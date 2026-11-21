#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 w4tchd0g (DM5LF)
# SPDX-License-Identifier: CERN-OHL-P-2.0
"""RF line and SMA launch calculation for the phenix-1255-shield-v2.

1. Impedance of the 50 ohm CPWG on F.Cu (JLC04161H-7628, reference In1):
   - closed-form model (conformal mapping after Wadell, thickness
     correction after Gupta), standard library only
   - 2D electrostatic field solver (finite differences), needs numpy and scipy
2. Excess capacitance of the through-hole launch of the vertical SMA jacks
   J5/J6 (Kinghelm KH-SMA-KE-Z): plated hole, pad rings on F.Cu and B.Cu,
   antipads on In1/In2, centre pin below the board. Axisymmetric (r, z)
   field solver; closed-form via estimate without numpy/scipy.
3. Shunt elements at the SMA ports (TVS, 100 nH, SMA launch).
4. Matching networks at the SX1255: TX 100 -> 50 ohm (C13/L2),
   RX 50 -> 200 ohm (L4/L3 plus the capacitance at RF_IN), both with the
   layout parasitics of the high-impedance nodes.

Run:  python3 scripts/rf_calc.py
      (field solver part is skipped if numpy/scipy are missing)
"""
import math

C0 = 299792458.0
E0 = 8.8541878128e-12

# Stackup (phenix-1255-shield-v2.kicad_pcb, JLC04161H-7628), mm
H = 0.2104      # prepreg F.Cu -> In1
T = 0.035       # outer copper
ER = 4.4        # prepreg 7628
MASK = 0.015    # solder mask thickness used in the field solver
ER_MASK = 3.8

# Geometry, mm
LINE = (0.30, 0.30)          # track width, gap to GND fill
LINE_IC = (0.30, 0.20)       # inside the SX1255 courtyard
PAD_D = 1.8                  # centre pad ring of J5/J6 on F.Cu and B.Cu
PAD_GAP = 0.30               # ring to the F.Cu / B.Cu GND fill (RF clearance)
DRILL = 1.2                  # centre hole (plated, filled with pin and solder)
ANTIPAD = 2.4                # keep-out on In1 / In2
PIN_D, PIN_L = 0.9, 4.0      # centre pin below the flange (sits on F.Cu)
POST_R = 2.54 * math.sqrt(2)  # GND posts on a 5.08 mm square: outer ground
T_IN = 0.0152                # inner copper (0.5 oz)
CORE = 1.065                 # core between In1 and In2 (JLC04161H-7628)
L_SHUNT = 100e-9             # DC shunt at each port (L1 / L5)
FREQS = (430e6, 440e6)
Z0 = 50.0


# --- closed-form CPWG ----------------------------------------------------
def ellip_k(k):
    a, b = 1.0, math.sqrt(1 - k * k)
    for _ in range(40):
        a, b = (a + b) / 2, math.sqrt(a * b)
    return math.pi / (2 * a)


def cpwg_closed(w, s, h, er, t=0.0):
    if t > 0:
        d = 1.25 * t / math.pi * (1 + math.log(4 * math.pi * w / t))
        w, s = w + d, s - d
    k = w / (w + 2 * s)
    k3 = math.tanh(math.pi * w / (4 * h)) / math.tanh(math.pi * (w + 2 * s) / (4 * h))
    r1 = ellip_k(k) / ellip_k(math.sqrt(1 - k * k))
    r3 = ellip_k(k3) / ellip_k(math.sqrt(1 - k3 * k3))
    q = r3 / r1
    eeff = (1 + er * q) / (1 + q)
    z = 60 * math.pi / math.sqrt(eeff) / (r1 + r3)
    return z, eeff


# --- 2D field solver -----------------------------------------------------
def cpwg_field(w, s, h, t, er, mask=0.0, d=0.005, x_max=3.0, y_air=2.0):
    """Half cross-section (symmetry plane at x = 0), grid step d (mm).
    Returns Z0 (ohm), eps_eff and C' (F/m)."""
    import numpy as np
    import scipy.sparse as sp
    import scipy.sparse.linalg as spl

    nh, nt, nm = round(h / d), round(t / d), round(mask / d)
    nx, ny = round(x_max / d) + 1, nh + nt + round(y_air / d) + 1
    iw, ig = round(w / 2 / d), round((w / 2 + s) / d)

    sig = np.zeros((nx, ny), bool)
    gnd = np.zeros((nx, ny), bool)
    sig[: iw + 1, nh: nh + nt + 1] = True
    gnd[ig:, nh: nh + nt + 1] = True             # coplanar ground
    gnd[:, 0] = gnd[:, -1] = gnd[-1, :] = True   # In1 and outer box

    def permittivity(er_sub, er_mask):
        e = np.ones((nx - 1, ny - 1))
        e[:, :nh] = er_sub
        if nm:
            for i in range(nx - 1):
                top = nh + nt if (i < iw or i >= ig) else nh
                e[i, top: top + nm] = er_mask
            e[iw: iw + nm, nh: nh + nt] = er_mask
            e[ig - nm: ig, nh: nh + nt] = er_mask
        return e

    def capacitance(e):
        ep = np.pad(e, 1)
        cv = (ep[0:nx, 1:ny] + ep[1:nx + 1, 1:ny]) / 2   # edges (i,j)-(i,j+1)
        ch = (ep[1:nx, 0:ny] + ep[1:nx, 1:ny + 1]) / 2   # edges (i,j)-(i+1,j)
        fixed = sig | gnd
        v = np.where(sig, 1.0, 0.0)
        idx = -np.ones((nx, ny), int)
        idx[~fixed] = np.arange((~fixed).sum())
        n = (~fixed).sum()
        rows, cols, vals = [], [], []
        b, diag = np.zeros(n), np.zeros(n)

        def add(ai, aj, bi, bj, c):
            a, bb = idx[ai, aj], idx[bi, bj]
            for p, q, qi, qj in ((a, bb, bi, bj), (bb, a, ai, aj)):
                m = p >= 0
                np.add.at(diag, p[m], c[m])
                mq = m & (q >= 0)
                rows.append(p[mq]); cols.append(q[mq]); vals.append(-c[mq])
                mf = m & (q < 0)
                np.add.at(b, p[mf], c[mf] * v[qi[mf], qj[mf]])

        i, j = np.meshgrid(np.arange(nx), np.arange(ny - 1), indexing="ij")
        add(i.ravel(), j.ravel(), i.ravel(), j.ravel() + 1, cv.ravel())
        i, j = np.meshgrid(np.arange(nx - 1), np.arange(ny), indexing="ij")
        add(i.ravel(), j.ravel(), i.ravel() + 1, j.ravel(), ch.ravel())
        rows.append(np.arange(n)); cols.append(np.arange(n)); vals.append(diag)
        a = sp.csc_matrix((np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))), shape=(n, n))
        v[~fixed] = spl.spsolve(a, b)
        energy = (cv * np.diff(v, axis=1) ** 2).sum() + (ch * np.diff(v, axis=0) ** 2).sum()
        return 2 * energy * E0   # both halves, V = 1

    c = capacitance(permittivity(er, ER_MASK))
    ca = capacitance(permittivity(1.0, 1.0))
    return 1 / (C0 * math.sqrt(c * ca)), c / ca, c


# --- SMA launch (through hole) -----------------------------------------------
def c_per_m(z, eeff):
    return math.sqrt(eeff) / (C0 * z)


def launch_closed():
    """Plated hole as a via (Johnson/Graham): C = 1.41 er T D1 / (D2 - D1),
    T, D in inches, C in pF; D1 = hole, D2 = antipad."""
    board = 2 * H + 2 * T_IN + CORE
    return 1.41 * ER * board / 25.4 * DRILL / (ANTIPAD - DRILL) * 1e-12


def launch_field(d=0.01):
    """Axisymmetric (r, z) finite-difference solver for the SMA launch.
    Signal: plated hole, pad rings on F.Cu / B.Cu, centre pin below the
    board. Ground: F.Cu / B.Cu fill beyond the ring gap, In1 / In2 beyond
    the antipad, the GND posts as the outer boundary at POST_R. Above the
    board air (the jack itself is not modelled). Returns C in F."""
    import numpy as np
    import scipy.sparse as sp
    import scipy.sparse.linalg as spl

    board = 2 * H + 2 * T_IN + CORE
    z0, z1 = -1.0, -T + PIN_L + 0.6
    nr, nz = round(POST_R / d) + 1, round((z1 - z0) / d) + 1
    r = np.arange(nr) * d
    z = z0 + np.arange(nz) * d
    rr, zz = np.meshgrid(r, z, indexing="ij")

    def band(a, b):
        return (zz >= a - 1e-9) & (zz <= b + 1e-9)

    ring = rr <= PAD_D / 2 + 1e-9
    sig = (rr <= DRILL / 2 + 1e-9) & band(-T, board + T)
    sig |= ring & (band(-T, 0) | band(board, board + T))
    sig |= (rr <= PIN_D / 2 + 1e-9) & band(board + T, -T + PIN_L)
    fill = rr >= PAD_D / 2 + PAD_GAP - 1e-9
    plane = rr >= ANTIPAD / 2 - 1e-9
    gnd = fill & (band(-T, 0) | band(board, board + T))
    gnd |= plane & (band(H, H + T_IN) | band(board - H - T_IN, board - H))
    gnd[-1, :] = True
    gnd &= ~sig

    zc = z0 + (np.arange(nz - 1) + 0.5) * d                  # cell centres
    eps_c = np.where((zc > 0) & (zc < board), ER, 1.0)       # depends on z only
    eps = np.broadcast_to(eps_c, (nr - 1, nz - 1))
    epad = np.pad(eps, 1)                                    # zero outside
    # radial edges (i, j) - (i + 1, j)
    rm = (np.arange(nr - 1) + 0.5) * d
    gr = 2 * np.pi * rm[:, None] * (epad[1:nr, 0:nz] + epad[1:nr, 1:nz + 1]) / 2
    # axial edges (i, j) - (i, j + 1): inner and outer half annulus of node i
    a_in = np.pi * (r ** 2 - np.clip(r - d / 2, 0, None) ** 2)
    a_out = np.pi * ((r + d / 2) ** 2 - r ** 2)
    gz = (epad[0:nr, 1:nz] * a_in[:, None] + epad[1:nr + 1, 1:nz] * a_out[:, None]) / d

    fixed = sig | gnd
    v = np.where(sig, 1.0, 0.0)
    idx = -np.ones((nr, nz), int)
    idx[~fixed] = np.arange((~fixed).sum())
    n = (~fixed).sum()
    rows, cols, vals = [], [], []
    b, diag = np.zeros(n), np.zeros(n)

    def add(ai, aj, bi, bj, c):
        a, bb = idx[ai, aj], idx[bi, bj]
        for p, q, qi, qj in ((a, bb, bi, bj), (bb, a, ai, aj)):
            m = p >= 0
            np.add.at(diag, p[m], c[m])
            mq = m & (q >= 0)
            rows.append(p[mq]); cols.append(q[mq]); vals.append(-c[mq])
            mf = m & (q < 0)
            np.add.at(b, p[mf], c[mf] * v[qi[mf], qj[mf]])

    i, j = np.meshgrid(np.arange(nr - 1), np.arange(nz), indexing="ij")
    add(i.ravel(), j.ravel(), i.ravel() + 1, j.ravel(), gr.ravel())
    i, j = np.meshgrid(np.arange(nr), np.arange(nz - 1), indexing="ij")
    add(i.ravel(), j.ravel(), i.ravel(), j.ravel() + 1, gz.ravel())
    rows.append(np.arange(n)); cols.append(np.arange(n)); vals.append(diag)
    a = sp.csc_matrix((np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))), shape=(n, n))
    v[~fixed] = spl.spsolve(a, b)
    energy = (gr * np.diff(v, axis=0) ** 2).sum() + (gz * np.diff(v, axis=1) ** 2).sum()
    return energy * E0 * 1e-3     # lengths in mm


def launch_excess(c_launch, c_line):
    """The 50 ohm track runs on the top ring up to the hole centre; that
    half ring diameter of line is part of c_launch already."""
    return c_launch - c_line * PAD_D / 2 * 1e-3


def main():
    print("CPWG on F.Cu, h = %.4f mm, t = %.3f mm, er = %.1f" % (H, T, ER))
    print("\nClosed-form (Wadell, Gupta thickness correction):")
    for w, s in (LINE, LINE_IC):
        z, e = cpwg_closed(w, s, H, ER, T)
        print(f"  w = {w:.2f} / s = {s:.2f} mm: Z0 = {z:.1f} ohm, eps_eff = {e:.2f}")
    sweep = ", ".join(f"{w:.2f} mm: {cpwg_closed(w, LINE[1], H, ER, T)[0]:.1f} ohm" for w in (0.25, 0.30, 0.35, 0.40))
    print(f"  width sweep at s = {LINE[1]:.2f} mm: {sweep}")
    c_line = c_per_m(*cpwg_closed(*LINE, H, ER, T))
    c_pad = launch_excess(launch_closed(), c_line)

    try:
        import numpy  # noqa: F401
        import scipy  # noqa: F401
        have_fd = True
    except ImportError:
        have_fd = False
        print("\n(numpy/scipy not found, field solvers skipped, SMA launch uses the via formula)")

    if have_fd:
        print("\n2D field solver (5 um grid):")
        for w, s in (LINE, LINE_IC):
            for m in (0.0, MASK):
                z, e, _ = cpwg_field(w, s, H, T, ER, m)
                tag = f"with {MASK * 1e3:.0f} um mask" if m else "bare copper"
                g = abs(z - Z0) / (z + Z0)
                print(f"  w = {w:.2f} / s = {s:.2f} mm, {tag:>16}: Z0 = {z:.1f} ohm, eps_eff = {e:.2f}, "
                      f"RL vs 50 ohm = {-20 * math.log10(g):.0f} dB")
        c_line = cpwg_field(*LINE, H, T, ER)[2]
        c_launch = launch_field()
        print(f"\nAxisymmetric field solver, SMA launch (10 um grid): C = {c_launch * 1e12:.2f} pF "
              f"(via formula: {launch_closed() * 1e12:.2f} pF)")
        c_pad = launch_excess(c_launch, c_line)

    print(f"\nSMA launch J5/J6 (hole {DRILL:.1f} mm, ring {PAD_D:.1f} mm, antipad {ANTIPAD:.1f} mm, "
          f"pin {PIN_L - (2 * H + 2 * T_IN + CORE) - 2 * T:.1f} mm below the board): excess capacitance about "
          f"{c_pad * 1e12:.2f} pF")
    for f in FREQS:
        b = 2 * math.pi * f * c_pad
        print(f"  {f / 1e6:.0f} MHz: X_C = {1 / b:.0f} ohm, RL on its own = {rl_shunt(b):.1f} dB")

    print_port(c_pad)
    print_matching()


# --- ports: TVS + 100 nH + SMA launch -------------------------------------
C_TVS = 0.4e-12   # PESD5V0F1BL


def print_port(c_pad):
    print("\nShunt elements at the SMA ports (TVS 0.4 pF, 100 nH, SMA launch), on a matched 50 ohm line:")
    for f, port in ((440e6, "TX"), (430e6, "RX")):
        b_l = -1 / (2 * math.pi * f * L_SHUNT)
        b_tvs = 2 * math.pi * f * C_TVS
        b_pad = 2 * math.pi * f * c_pad
        parts = []
        for label, b in (("TVS + 100 nH", b_l + b_tvs), ("with SMA launch", b_l + b_tvs + b_pad)):
            parts.append(f"{label}: B = {b * 1e3:+.2f} mS, RL = {rl_shunt(b):.0f} dB")
        print(f"  {port} {f / 1e6:.0f} MHz: " + "; ".join(parts))


def rl_shunt(b):
    y = complex(1 / Z0, b)
    g = abs((1 / y - Z0) / (1 / y + Z0))
    return -20 * math.log10(g)


# --- matching networks at the SX1255 ----------------------------------------
def zc(c, f):
    return 1 / (2j * math.pi * f * c)


def zl(l, f):
    return 2j * math.pi * f * l


def par(a, b):
    return a * b / (a + b)


def rl(z, z0):
    return -20 * math.log10(abs((z - z0) / (z + z0)))


def lnet(r_high, r_low, f):
    """Low-pass L-network: shunt C at the high side, series L at the low side."""
    q = math.sqrt(r_high / r_low - 1)
    return q, 1 / (2 * math.pi * f * r_high / q), q * r_low / (2 * math.pi * f)


# Component values and layout parasitics of the matching networks.
# The parasitics were estimated from the layout (2026-11-21): track length
# times C' of the CPWG (field solver, with mask) plus the excess capacitance
# of the pads (pads as wide CPWG sections). At the high-impedance nodes the
# short tracks act as shunt capacitance.
C13, L2, C14 = 2.2e-12, 18e-9, 100e-12
C13_ESL = 0.6e-9             # 0603 capacitor, raises its effective value slightly
C_PAR_TX = 1.20e-12          # C13 node 0.71 pF + RFO_P node 0.49 pF (C14 is 3.6 ohm)
L3, L4, C21 = 43e-9, 33e-9, 100e-12
C_LAY_RX = 1.22e-12          # RF_IN node: 7.3 mm track + pads of L3, L4, D4, IC1
C_MID_RX = 0.39e-12          # node between C21 and L4
C_BAV99 = (0, 3.0e-12)       # Nexperia BAV99: Cd <= 1.5 pF per diode, two in antiparallel


def c13_eff(f, c13=C13):
    w = 2 * math.pi * f
    return c13 / (1 - w * w * C13_ESL * c13) + C_PAR_TX


def tx_zin(f, c13=C13, l2=L2, c14=C14):
    """Impedance seen by RF_OP: C14 series, C13 (plus ESL and layout C) shunt,
    L2 series, LFCN-490+ as 50 ohm."""
    return zc(c14, f) + par(zc(c13_eff(f, c13), f), zl(l2, f) + Z0)


def tx_gain(f, c13=C13, l2=L2, c14=C14, rs=100.0):
    """Transducer gain from a 100 ohm source at RF_OP into 50 ohm (dB)."""
    zn = par(zc(c13_eff(f, c13), f), zl(l2, f) + Z0)
    zin = zc(c14, f) + zn
    v_load = zin / (rs + zin) * zn / zin * Z0 / (zl(l2, f) + Z0)
    return 10 * math.log10(abs(v_load) ** 2 / Z0 / (1 / (4 * rs)))


def rx_zin(f, c_tot, r_lna=200.0, l3=L3, l4=L4, c21=C21, c_mid=C_MID_RX):
    """Impedance seen by the SAW output: C21 series, shunt C_MID_RX, L4 series,
    then L3 shunt, total shunt capacitance at RF_IN (pin, BAV99, layout) and
    the 200 ohm LNA."""
    zp = 1 / (1 / r_lna + 2j * math.pi * f * c_tot + 1 / zl(l3, f))
    zb = zl(l4, f) + zp
    return zc(c21, f) + 1 / (1 / zb + 2j * math.pi * f * c_mid)


def print_matching():
    f = 440e6
    q, c, l = lnet(100, 50, f)
    print(f"\nTX matching at {f / 1e6:.0f} MHz, 100 ohm (RF_OP, RF_ON AC-grounded) -> 50 ohm (LFCN-490+):")
    print(f"  ideal L-network: Q = {q:.2f}, shunt C = {c * 1e12:.2f} pF, series L = {l * 1e9:.2f} nH")
    print(f"  used: C13 = {C13 * 1e12:.1f} pF (+ESL {C13_ESL * 1e9:.1f} nH) + layout {C_PAR_TX * 1e12:.2f} pF "
          f"= {c13_eff(f) * 1e12:.2f} pF, L2 = {L2 * 1e9:.0f} nH")
    print(f"  C14 / C15 (100 pF): X = {abs(zc(100e-12, f)).real:.1f} ohm")
    for ff in (400e6, 420e6, 440e6, 460e6, 480e6):
        z = tx_zin(ff)
        print(f"  {ff / 1e6:.0f} MHz: Z at RF_OP = {z.real:.1f} {z.imag:+.1f}j ohm, RL vs 100 ohm = {rl(z, 100):.1f} dB")
    worst = min(rl(tx_zin(ff, c13, l2), 100) for ff in (430e6, 440e6, 450e6)
                for c13 in (C13 - 0.25e-12, C13 + 0.25e-12) for l2 in (L2 * 0.98, L2 * 1.02))
    print(f"  tolerances (C13 +-0.25 pF, L2 +-2 %, 430-450 MHz): RL >= {worst:.1f} dB")
    print(f"  with C13 = 3.6 pF (previous value) the RL at 440 MHz would be {rl(tx_zin(f, 3.6e-12), 100):.1f} dB")
    print("  extra low-pass effect of the L-network: " + ", ".join(
        f"{n}f0 {tx_gain(n * f):.1f} dB" for n in (1, 2, 3)))

    f = 430e6
    w = 2 * math.pi * f
    q, c, l = lnet(200, 50, f)
    print(f"\nRX matching at {f / 1e6:.0f} MHz, 50 ohm (SF2446E) -> 200 ohm (LNA, LnaZin = 1):")
    print(f"  ideal L-network: Q = {q:.2f}, series L = {l * 1e9:.2f} nH, shunt C = {c * 1e12:.2f} pF")
    z_series = zc(C21, f) + zl(L4, f)
    y_pin = 1 / (Z0 - z_series)
    c_tot = (y_pin.imag + 1 / (w * L3)) / w
    print(f"  with C21 = 100 pF and L4 = 33 nH the RF_IN node must show Y = {y_pin.real * 1e3:.2f} mS "
          f"(R = {1 / y_pin.real:.0f} ohm) {y_pin.imag * 1e3:+.2f}j mS")
    print(f"  L3 = {L3 * 1e9:.0f} nH cancels {1 / (w * w * L3) * 1e12:.2f} pF, so the total capacitance "
          f"at RF_IN must be {c_tot * 1e12:.2f} pF")
    y_ref = 1 / (Z0 - zl(39e-9, f))
    c_ref = (y_ref.imag + 1 / (w * 82e-9)) / w
    print(f"  expected: chip + its layout about {c_ref * 1e12:.1f} pF (implied by 39 nH / 82 nH without limiter), "
          f"BAV99 {C_BAV99[0] * 1e12:.0f}-{C_BAV99[1] * 1e12:.0f} pF, extra layout here {C_LAY_RX * 1e12:.2f} pF")
    for ct in (5.0e-12, 5.5e-12, 6.0e-12, c_tot, 7.0e-12, 7.5e-12, 8.0e-12):
        best = max(range(360, 521), key=lambda m: rl(rx_zin(m * 1e6, ct), Z0))
        print(f"    C_tot = {ct * 1e12:.2f} pF: RL at 430 MHz = {rl(rx_zin(f, ct), Z0):.1f} dB, best match at {best} MHz")
    print("  L3 for a match at 430 MHz if C_tot differs: " + ", ".join(
        f"{ct * 1e12:.0f} pF -> {1 / (w * (w * ct - y_pin.imag)) * 1e9:.0f} nH"
        for ct in (5e-12, 6e-12, 7e-12, 8e-12)))
    band = [ff for ff in range(380, 481) if rl(rx_zin(ff * 1e6, c_tot), Z0) >= 20]
    print(f"  RL >= 20 dB from {band[0]} to {band[-1]} MHz (C_tot = {c_tot * 1e12:.2f} pF)")


if __name__ == "__main__":
    main()
