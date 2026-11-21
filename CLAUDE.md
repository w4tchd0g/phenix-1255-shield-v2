# CLAUDE.md

Working notes for phenix-1255-shield-v2: revision V2 of an SX1255 RF shield for the NXP FRDM-MCXN947 (KiCad 10). V1 is [phenix-1255-shield](https://github.com/w4tchd0g/phenix-1255-shield) (local copy in `../phenix-1255-shield`); V2 was copied from it on 2026-11-21 and renamed. It is the hardware part of [phenix-1255-sw](https://github.com/w4tchd0g/phenix-1255-sw) and a modified version of [Phenix-1255-HW](https://github.com/labdvm/Phenix-1255-HW) by Z32IT. `README.md` covers what the project is, the circuit, the pin assignment, fabrication and bring-up. This file holds everything else: conventions, settled decisions, known warnings, layout details and the background of the RF calculations.

## Conventions

- The user writes in German. Answer in German.
- Write all repository content in English: README, CLAUDE.md, comments in scripts and in the design rules.
- Keep the README limited to what matters for building and using the board. Put layout conventions, tool details and derivations here.
- After every layout change, run `./scripts/gerber.sh` and `./scripts/render.sh` and update the README where needed. After part changes also run `./scripts/assembly.sh`. Commit only when the user asks.
- Keep the README chapter *Changes from V1* up to date with every change that differs from V1.

## Tools

- `kicad-cli`: `/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli` (not on `PATH`). The scripts find it on their own.
- Python with the `pcbnew` module: `/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3`. The assertion `create wxApp before calling this` on stderr is harmless. Without a wxApp, text bounding boxes of rotated text are not reliable; calculate them by hand (stroke font: 1.0 mm text ≈ 1.14 mm high including stroke, "S1" ≈ 2.27 mm wide).
- The shell is zsh: `set -- $var` does not split words there. Use `bash -c` for loops of that kind.
- Checks:
  - ERC: `kicad-cli sch erc --severity-all phenix-1255-shield-v2.kicad_sch`
  - DRC: `kicad-cli pcb drc --schematic-parity --severity-all phenix-1255-shield-v2.kicad_pcb`
- Visual check of silkscreen and mask: `kicad-cli pcb export svg --layers F.Mask,F.SilkS,Edge.Cuts --mode-single --exclude-drawing-sheet` (without `--fit-page-to-board`, so SVG coordinates are board coordinates), then set the `viewBox` to the area of interest and convert with `rsvg-convert` (Homebrew).

### Scripts

- `scripts/gerber.sh`: runs the DRC (aborts on errors or unconnected items), exports Gerber with JLCPCB settings (Protel extensions, `--subtract-soldermask`, no X2, no netlist, `--check-zones`) and Excellon drill files (mm, decimal, PTH/NPTH separate, alternate oval format), renames the Altium-style layer names (`Top Layer`, `GND`, `PWR`, …) to `F_Cu`, `In1_Cu`, … and zips everything except the drill maps into `production/phenix-1255-shield-v2-gerber.zip`. JLCPCB and PCBWay both take this file set (Protel extensions, `.g1`/`.g2` for the inner layers).
- `scripts/assembly.sh`: exports `production/phenix-1255-shield-v2-bom.csv` (from the schematic) and `production/phenix-1255-shield-v2-cpl.csv` (from the PCB) for JLCPCB assembly, both without DNP parts. `scripts/jlc_csv.py` groups the BOM (comment: value for C/R/L, otherwise MPN), writes the JLCPCB column names and adds the rotation offsets (`ROTATION_OFFSET`: SOT-23* +180°, SX1255 QFN +270°; common values for KiCad footprints, not verified against a JLCPCB order). It aborts if the part lists of schematic and PCB differ. Run it after changes to parts, `LCSC` fields, DNP flags or placement.
- `scripts/render.sh`: renders `docs/img/` with `kicad-cli pcb render`. It uses a temporary copy of the KiCad configuration in which all 3D model types are visible, so the images do not depend on the GUI settings. `scripts/trim.py` crops each image to the board and its shadow (needs Pillow or wxPython; on macOS the KiCad Python is used). Images trimmed in one call get the same crop box.
- `scripts/rf_calc.py`: all RF numbers (see [RF calculation details](#rf-calculation-details)).
- `scripts/make_3d_models.py`: generates the own 3D models (see [External components](#external-components)).

### Editing the board file directly

- All footprints are locked. Edits by script or `sed` are fine, but read the affected block first.
- In a footprint, the `at` of a property or text is footprint-relative (rotated with the footprint), but its angle is absolute. Example: S1–S3 are rotated 180°, and their reference is at `(at 4.3 0 90)`.
- When the graphics of a footprint change on the board, make the same change in the library footprint in `ext_parts/`, otherwise *Update footprints from library* reverts it. Exception: reference positions only live on the board; do not tick *Reset text positions* when updating.

## Settled decisions (do not flag again)

- **SX_RST** (IC1.9 → J1.6) has no pull resistor. The SX1255 datasheet requires it to be left open; the MCU drives it high only to reset.
- **38.4 MHz TCXO** is outside the SX1255 FXOSC range but has been tested by the user and works. Mention it neutrally at most.
- **Buttons S1–S3 and jumpers JP1–JP3** use the MCU internal pull-downs; no external pull-downs.
- **Display DS1** has on-board I²C pull-ups.
- **R20** (0 Ω between QOD and VOUT of U2) is fitted, so VBAT3 is discharged while the PA is off, as in V1. Remove it only if the bring-up measurement shows current from the SX1255 into VBAT3.
- **RX SAW filter FL2 (TA1651A)**: passband 420–436 MHz; 439–440 MHz (TX) lies on its upper edge (about 3.5–6 dB in total according to the datasheet plot), so it gives practically no TX rejection in the RX path. Decided by the user on 2026-11-21: an external duplexer connected to J5/J6 provides the TX/RX isolation. Operating frequencies: RX about 431 MHz, TX about 439 MHz. A discrete 2–3 pole LC band-pass was considered and rejected (1.5–3 dB more loss, 15–25 dB instead of ≥ 45 dB at 380–395 MHz, no rejection at 439 MHz either).
- **`~PA_EN`**: 100 kΩ pull-up to `+3v3` (FRDM domain), driven by an MCU GPIO. U2 is the TPS22917L with active-low enable.
- **Headers J1–J4, J8, J9** come from the template. Footprint, library and field issues on them are out of scope.
- **Missing MPNs / part numbers** (FL1, DS1, and the PCB-side `MPN` fields) are not part of reviews.
- **JLCPCB part numbers** (`LCSC` field, reviewed 2026-11-16): Basic parts are used where an equivalent exists (resistors, 100 pF, 100 nF, 1 µF, BAV99). The 10 nF capacitors stay C0G (Extended, `C2215227`) because of the LDO bypass pin and the TCXO coupling. The LEDs are Everlight 19-21 (0603, Extended), chosen by the user: green `C2986048`, red `C2986050`, yellow `C2986008`. The SMA jacks J5/J6 are the Kinghelm KH-SMA-KE-Z (`C504007`, Extended, through hole, wave soldering at JLCPCB), chosen by the user on 2026-11-21. The RX SAW filter FL2 is the Tai-Saw TA1651A (`C5224551`, chosen by the user on 2026-11-21), also placed by JLCPCB. It replaced the Murata (RFMi) SF2446E the same day, which JLCPCB could not place (the SF2446E had replaced the V1 part TA0655A). The TCXO Y1 is the Epson TG2016SMN 38.4000M-MCGNNM3 (`C1987359`, Extended), chosen by the user on 2026-11-21 because the TG2520SMN (`C20341495`) was not available; same suffix, so the electrical data are the same. DS1 and the headers are not in the JLCPCB library and are *Do not populate* in the schematic and on the PCB (the 3D renderings still show them).
- Reference designators were re-annotated on 2026-11-04. Identify parts by net and value when reading older notes.

## Known ERC/DRC warnings

- **ERC:** no errors.
  - Warnings come from unused template labels and wire stubs at the headers (`isolated_pin_label`, `unconnected_wire_endpoint`), from header pins with two names (`multiple_net_names`), and from the template header symbols without a library nickname (`footprint_link_issues`).
  - The `PWR_FLAG`s for `+3v3`, `+5v0`, `GND`, `5v-9v-IN` and `VDDA` sit in the root schematic next to the sheet symbol.
  - 162 warnings in total. The former exclusion of the `pin_to_pin` warning U2 QOD ↔ VOUT was removed on 2026-11-21: since R20 sits between QOD and VOUT, the two pins are on different nets and the warning no longer occurs.
- **DRC:** no errors, 0 unconnected pads. The 130 warnings are:
  - 124 × `padstack` on the header THT pads (negative paste margin), harmless.
  - 6 × `lib_footprint_issues`: the libraries `FRDM-MCXN947__Template__A.PcbLib` and `Wavenumber` of the template headers are not in `fp-lib-table`.
- **Ignored checks** in the project: `missing_courtyard` (only the template headers and the logo have none), `pth_inside_courtyard`, `npth_inside_courtyard`, `track_not_centered_on_via`, `footprint_type_mismatch`, `footprint_filters_mismatch`. Enabling them on a copy shows nothing beyond the missing courtyards.
- **Schematic parity:** no net or footprint mismatches. Remaining differences:
  - field mismatches (`MPN`, `Description`, `Sim.Pins`, `Height`, …);
  - JP1–JP3 values (`JP1` on the PCB vs. `0` in the schematic);
  - the header footprint names have a library nickname on the PCB only.
- **Update PCB from Schematic:** untick *Delete footprints with no symbols* (otherwise the logo is deleted) and *Replace footprints* (the header symbols have no library nickname).
- **Plane splits on In2:** DIO1, DIO2/WS, DIO3 and NSS (SX1255 side) on B.Cu cross gaps between the In2 areas. This is uncritical at their speeds.

## Layout details

### Net classes and rules

| Class | Nets | Track | Clearance | Via (Ø / drill) |
|---|---|---|---|---|
| Default | everything else | 0.2 mm | 0.2 mm | 0.6 / 0.3 mm |
| RF | `RF_*` and the nets between SX1255, matching, filters and SMA | 0.3 mm | 0.3 mm | – (no vias allowed) |
| PWR_5V | `+5v0`, `5v-9v-IN` | 0.5 mm | 0.2 mm | 0.8 / 0.4 mm |
| PWR_3V3 | `+3v3`, `+3.3V_LDO`, `VBAT3`, `VDDA` | 0.4 mm | 0.2 mm | 0.8 / 0.4 mm |
| GND | `GND` | 0.4 mm | 0.2 mm | 0.6 / 0.3 mm |

- The vias actually placed on the power nets are mostly 0.6 / 0.3 mm (`+3.3V_LDO` 17×, `+5v0` 2×, `+3v3` 2×; three `+3v3` vias are 0.8 / 0.4 mm). This is sufficient for the currents involved.
- Board minimums: 0.15 mm track, clearance and annular ring; 0.5 mm via diameter; 0.3 mm drill; 0.5 mm copper to edge; 0.25 mm hole to hole. Silkscreen text is at least 1.0 mm high and 0.15 mm thick.

`phenix-1255-shield-v2.kicad_dru` adds rules that the net classes cannot express. KiCad 10 needs a unit on every value, otherwise the whole file is rejected.

- **RF:** no vias, and no tracks on the inner layers or B.Cu (the reference there would be the power plane).
- **SX1255 fine pitch:** inside the IC1 courtyard the RF clearance drops to 0.2 mm, pad-to-pad within IC1 to 0.15 mm (the corner pads are 0.177 mm apart). Non-RF tracks may neck down to 0.15 mm (opt. 0.25 mm) there.
- **Solid GND at RF parts:** the GND pads of IC1, FL*, D1/D4/D8 connect without thermal reliefs.
- **SMA THT GND thermal:** the through-hole GND posts of J5/J6 use thermal reliefs on all layers (0.8 mm spokes, 0.3 mm gap) so they can be soldered.
- **Stitching vias:** at least 0.25 mm between drill holes (JLCPCB minimum 0.2 mm).

### Ground and stitching

The GND fills on all four layers are tied together with 319 GND vias (0.6 / 0.3 mm):

- **Via fences** along both RF lines (0.8 mm from the line, 0.765 mm pitch, radially paired in the bends), between J5 and J6, and around the J5/J6 ground pads.
  - FL2 sits as far from the bend of the RX line as C21 (part centre to the start of the bend 3.42 mm). On both sides of both parts the fence ends 2.20 mm from the part centre. Between FL2 and L5 the pairs are spaced 0.766 mm, above L1 0.715 mm; both fences end 1.41 mm (RX) and 1.20 mm (TX) above the centre of L5/L1.
- **Pad vias:** each ground pad of the decoupling capacitors, the TCXO, the LDO, the load switch, the TVS diodes and the TX filter has its own via.
- **Stitching grid:** 7.62 mm grid centred on the board centre (148.50 / 105.00 mm).
  - Grid points that would hit pads, tracks, courtyards, header rows, silkscreen, the framed function blocks or the B.Cu logo are left out.
  - Six formally free points stay empty: 148.50 / 97.38 and 171.36 / 97.38 (too close to the C10 and FL1 labels), 178.98 / 120.24 and 194.22 / 120.24 (too close to the L5 and L1 labels since the SMA groups moved up), and 110.40 / 89.76 and 118.02 / 89.76 (too close to the DS1 outline and the SDA track).
  - One extra via at 186.60 / 94.51 mm ties the fill between the `HW_ID_1` and `HW_ID_2` tracks to GND.
- **No islands:** each fill area large enough for a via is tied to GND. The zones use *Remove islands: Always*, so no floating copper is left.

### SX1255 footprint

`ext_parts/SX1255IWLTRT.pretty` follows the recommended land pattern of the SX1255 datasheet Rev. 3.1, figure 7-2: pads 0.30 × 0.80 mm on a 4.90 mm row pitch, exposed pad 3.30 × 3.30 mm (the package pad is 3.10 mm nominal). It has 9 thermal vias (0.6 / 0.3 mm) in the exposed pad, arranged as a cross: centre, ±0.6 mm and ±1.2 mm on both axes (0.3 mm between the drill holes). The paste on the exposed pad is 4 squares of 1.246 × 1.246 mm, one per quadrant (x/y 0.352 … 1.598 mm), 57 % of the 3.3 mm land (about 65 % of the nominal 3.1 mm package pad); they keep 0.052 mm from the via pads (about 0.2 mm from the drill holes) and from the edge of the exposed pad. This is the maximum with the cross of vias. The datasheet (Rev. 3.0, figure 23) gives no paste coverage; 50–80 % is common practice. Changed on 2026-11-21 from a 3 × 3 via grid with 8 irregular paste openings.

### Silkscreen

- **Reference designators:** 1.0 mm high, 0.17 mm thick (JLCPCB: at least 1.0 mm / 0.153 mm).
  - They run parallel to the part, centred on its axis, 0.4 mm from pads and part silkscreen, preferably in line with the part.
  - Rows of equal parts are labelled on the same side. Labels may lie on tented vias.
  - Distances refer to the visible text outline, stroke included.
  - J1–J4 and J9 labels sit vertically centred beside their header, J8 below it.
- **Exceptions:**
  - C2 and C3: 0.3 mm from their pads, because the row above (D2, R1) leaves no more room. Both labels are at the same height.
  - R1: at the same height as D2 (LED and series resistor of the PWR LED), therefore 0.6 mm from its own silkscreen.
  - IC1: left of the part near its upper end, in the resistor column above R3, centred between R3 and the pads of C10/C11 (0.61 mm on both sides). This puts it 1.0 mm from the IC1 pads and 3.0 mm above the IC1 axis. R3 and R6 sit at the height of the IC1 pins they connect to (pins 10 and 15), so there is no room for the label between them.
  - D4: left of the part and below its axis, because the courtyard and pads of IC1 are above it.
  - S1–S3: vertical (90°) on the left side of the switch, between pads 3 and 4, footprint-relative at x = 4.3, about 0.35 mm from the body outline.
  - S1–S3 pin-1 dot: below pad 1, centred between the end of the body outline and the end of the pad (footprint-relative −4.125 / −3.0), 0.26 mm from the pad. The same position is in the library footprint `EVQQ2`. The earlier position sat almost on pad 4 of the neighbouring switch.
  - DS1: outside the display outline at its top left, in line with the pin row (footprint-relative −15.81 / 0), 0.41 mm left of the outline, like the J2 label above it. Anything inside the outline is covered by the fitted module.
  - J5/J6: above the jack, 1.545 mm from the flange outline (the same distance as `RX`/`TX` beside the jacks), and 2.6 mm left of its axis, because L1/D1 and L5/D8 sit on the RF line above the jack centre.
  - R4 and R14: the "R" is flush with the neighbouring label (R5 beside R4, R13 below R14). Because the "4" is wider, both labels are 0.35 mm from their pads.
- **Hidden references:** JP1–JP3 (their labels are `0`–`2`), the logos `G***` and the fiducials FID1–FID3.
- **Fiducials:** FID1–FID3 (KiCad `Fiducial:Fiducial_1mm_Mask2mm`: 1 mm copper, 2 mm mask opening, 0.6 mm copper clearance), `board_only`, not in BOM or position file. Three corners top right (FID2), bottom right (FID1) and bottom left (FID3), each 3.0 mm from both edges (mask opening 2.0 mm from the edge); top left stays free (the `MCU-Link` label is in the way), so a rotated board is detected. 3.0 mm keeps them outside the corner points of the stitching grid (4.6–5.7 mm from the edges): ≥ 2.8 mm to copper, ≥ 2.0 mm to silkscreen.
- **Display pin labels** (`GND`, `VDD`, `SCL`, `SDA`) run vertically below the pins. The display outline is interrupted there, in the library footprint as well.
- **Edge labels:** `MCU-Link`, `Ethernet` and `HS-USB` on the left edge mark the FRDM connectors below. They are 1.5 mm from the board edge or cutout and centred in their section.
- **Button and LED labels:** button labels (`<--`, `OK`, `-->`) and LED labels (`OK`, `INFO`, `ERR`) are centred above their parts at the same height. The LEDs and their resistors sit on a 6.35 mm grid.
- **Function blocks:** `LDO`, `PA Enable` and `HW ID` are framed. `PA Enable` and `HW ID` share the top edge, and their labels sit at the same distance above it. The `+3v3` vias of the HW ID jumpers sit exactly halfway between the jumpers.
- **SMA labels:** `RX` and `TX`, vertical, centred on the jack axis, 1.545 mm from the jack outline (RX left of J6, TX right of J5).

### SMA land pattern (J5/J6)

`SMA_Kinghelm_KH-SMA-KE-Z_Vertical` (library `KH-SMA-KE-Z` in `ext_parts/KH-SMA-KE-Z.pretty`) for the Kinghelm KH-SMA-KE-Z (drawing 2019-06-06), a vertical through-hole SMA jack. It replaced the SMD jack KH-SMAK-SMT on 2026-11-21, because four SMD pads do not take the tightening torque; the SMD jack had replaced the hybrid land pattern (TE CONSMA001-SMD-G / Samtec edge mount) the same day.

- **Pads:** GND posts (pad 2, 0.9 mm square, diagonal 1.27 mm) on a 5.08 mm square: drill 1.5 mm, pad Ø2.4 mm (the drawing suggests 1.4 mm, too tight with the JLCPCB drill tolerance of ±0.08 mm; 1.5 mm keeps the jack from sitting crooked). Centre pin (pad 1, Ø0.9 mm): drill 1.2 mm, pad Ø1.8 mm on F.Cu and B.Cu only (`remove_unused_layers`, `keep_end_layers`).
- **Antipad:** rule areas (no copper pour, tracks or vias) of Ø2.4 mm on In1/In2 around the centre hole. On F.Cu/B.Cu the RF clearance of 0.3 mm gives the same 2.4 mm.
- **Placement:** the footprint origin (centre pin) is 5.04 mm from the board edge (flange 1.79 mm, GND pads 1.30 mm). On 2026-11-21 J5/J6 moved up by 1.27 mm together with D1/L1 and D8/L5, their labels, the RX/TX texts and the vias around them; afterwards the jacks with their via ring and the RX/TX texts moved back down by 0.635 mm. The J5/J6 references then got the same distance to the jack as RX/TX. The RF track ends at the pin centre. Pads are 0.34 mm from the fence vias.
- **GND posts** connect to all four GND layers through thermal reliefs (rule *SMA THT GND thermal*: 0.8 mm spokes, 0.3 mm gap), so they stay solderable with wave or hand soldering. Under both jacks all inner layers and B.Cu are GND fill, no tracks.
- **Silkscreen:** flange outline (6.5 mm) at ±3.45 mm, only between the pads. Courtyard 8 × 8 mm on F and B.
- **3D model:** `ext_parts/3d/KH-SMA-KE-Z.step` from `scripts/make_3d_models.py`: 6.5 mm flange, 1.5 mm thick, neck Ø5.2 mm, thread 6.2 mm, front face 9.5 mm above the board, posts and pin 4 mm below the flange; gold body, PTFE insulator recessed 2.0 mm. Flange and neck are read off the drawing, the recess is assumed.
- **Below the board:** the posts stick out about 2.4 mm under the shield. Nothing on the FRDM board under J5/J6 may touch them (not checked against the FRDM layout).

## RF calculation details

`scripts/rf_calc.py` reproduces all numbers below.

### CPWG impedance

- **Model:** CPWG on F.Cu over In1 at 0.2104 mm (prepreg 7628, εr 4.4), copper 35 µm. In1 has no cut-outs under the RF section. The coplanar ground is the F.Cu fill, tied to In1 by the via fences.
- **Closed form** (Wadell conformal mapping, Gupta thickness correction), gap 0.30 mm:

  | Track width | 0.25 mm | **0.30 mm** | 0.35 mm | 0.40 mm |
  |---|---|---|---|---|
  | Z0 | 54.7 Ω | **50.2 Ω** | 46.5 Ω | 43.3 Ω |

  The closed form gives εeff 3.19 for 0.30 / 0.30 mm, and 47.0 Ω at 0.30 / 0.20 mm (inside the IC1 courtyard).
- **Field solver:** 2D Laplace equation, finite differences, half cross-section with symmetry plane, 5 µm grid, 6 × 2.25 mm domain. Z0 = 1 / (c · √(C · C_air)). Halving the grid changes Z0 by less than 0.05 Ω.

  | Section | Bare copper | With 15 µm solder mask (εr 3.8) |
  |---|---|---|
  | 0.30 / 0.30 mm | 53.7 Ω, εeff 2.98 | **52.2 Ω**, εeff 3.15 |
  | 0.30 / 0.20 mm (IC1) | 51.6 Ω, εeff 2.88 | 49.9 Ω, εeff 3.07 |

- **Result:** about 52 Ω gives |Γ| ≈ 0.02, a return loss of about 33 dB and a mismatch loss below 0.01 dB.
  - The guided wavelength at 440 MHz is about 384 mm (εeff 3.15). The longest RF net (J5 to the TX filter, `Net-(D1-A2)`) is 38.9 mm long, about 36°.
  - An etching tolerance of ±0.03 mm shifts Z0 by ±2–3 Ω.
  - Not modelled: εr dispersion and tolerance, copper roughness.

### SMA launch (J5/J6)

The through-hole launch of J5/J6 adds capacitance to the 50 Ω line: plated hole Ø1.2 mm (filled with pin and solder), pad rings Ø1.8 mm on F.Cu and B.Cu with 0.3 mm gap to the fill, antipad Ø2.4 mm on In1/In2, centre pin 2.4 mm below the board.

- **Model:** axisymmetric (r, z) finite-difference solver, 10 µm grid (halving it changes C by about 1 %). Ground: F.Cu/B.Cu fill, In1/In2 outside the antipad, and the GND posts as the outer boundary (r = 3.59 mm). Above the board air; the jack itself is not modelled. Stack: 0.2104 mm prepreg, 15 µm inner copper, 1.065 mm core, εr 4.4 throughout.
- **Result:** 0.73 pF in total (the pin below the board adds about 0.07 pF). The 50 Ω track on the ring up to the pin centre (0.9 mm) is part of it, so the excess capacitance is about 0.64 pF: X_C ≈ 570 Ω at 440 MHz, return loss on its own 27 dB.
- **Comparison:** the via formula (Johnson/Graham, hole vs. antipad only) gives 0.37 pF; it ignores the pad rings and the pin.
- Not modelled: the transition into the jack itself (not specified by Kinghelm).

### Shunt elements at the ports

TVS D1/D8 (PESD5V0F1BL, 0.4 pF) + 100 nH (L1/L5) + SMA launch, on the 50 Ω line (negative = inductive). The launch capacitance largely cancels the 100 nH DC shunt (+j 276 Ω at 440 MHz, about 7 mm from the jack, i.e. at the same electrical point).

| Port | TVS + 100 nH | With SMA launch |
|---|---|---|
| TX, 440 MHz | −2.51 mS → RL 24 dB | −0.75 mS → RL 35 dB |
| RX, 430 MHz | −2.62 mS → RL 24 dB | −0.90 mS → RL 33 dB |

### Matching networks (supplement to the README)

Both networks include the layout parasitics of the high-impedance nodes (checked 2026-11-21): track length × C' of the CPWG with mask (113 pF/m, 117 pF/m inside the IC1 courtyard) plus the excess capacitance of the pads (pads as wide CPWG sections). The values are constants in `rf_calc.py` (`C_PAR_TX`, `C_LAY_RX`, `C_MID_RX`); recalculate them when the RF layout changes.

| Node | Track | Pads | Total |
|---|---|---|---|
| C13 node (C13, C14, L2) | 3.27 mm, 0.37 pF | 0.34 pF | 0.71 pF |
| RFO_P (IC1.30, C14) | 3.10 mm, 0.35 pF | 0.14 pF | 0.49 pF |
| RF_IN (IC1.27, L3, L4, D4) | 7.32 mm, 0.83 pF | 0.39 pF | 1.22 pF |
| C21/L4 | 1.49 mm, 0.17 pF | 0.22 pF | 0.39 pF |

- **TX** (R_H = 100 Ω, R_L = 50 Ω, 440 MHz, Q = √(R_H/R_L − 1) = 1.00). C14 is 3.6 Ω at 440 MHz, so the RFO_P node is in parallel with C13. C13 = 2.2 pF (ESL 0.6 nH) + 1.20 pF = 3.42 pF effective (ideal 3.62 pF). Changed from 3.6 pF on 2026-11-21 (with 3.6 pF: 89 − j34 Ω, RL 14.6 dB).

  | Frequency | Z at RF_OP | RL vs. 100 Ω |
  |---|---|---|
  | 400 MHz | 89.6 + j7.1 Ω | 23.5 dB |
  | 420 MHz | 94.3 + j4.8 Ω | 28.3 dB |
  | 440 MHz | 99.2 + j1.7 Ω | 40.6 dB |
  | 460 MHz | 104.1 − j2.4 Ω | 32.6 dB |
  | 480 MHz | 108.8 − j7.7 Ω | 25.1 dB |

- **RX** (Q = 1.73 at 430 MHz). With C21 and L4 in series, RF_IN must show Y = 5.10 mS + j8.72 mS (196 Ω in parallel with a capacitance). With L3 = 43 nH (3.19 pF compensated) the total capacitance at RF_IN must be 6.41 pF: 3.21 pF for the L-network, 3.19 pF compensated by L3, 0.01 pF for the deviation of L4/C21. Expected 6–8 pF: chip about 4.5 pF (implied by the reference values 39 nH series / 82 nH shunt), BAV99 up to 3 pF (Nexperia BAV99,215, `C2500`: Cd ≤ 1.5 pF per diode), layout 1.22 pF. L3 was 68 nH before (designed for 5.24 pF; with 6–7 pF the match would sit at 380–404 MHz).

## External components

Parts that are not in the KiCad standard libraries or the template live in `ext_parts/` and are registered in `sym-lib-table` / `fp-lib-table`.

| Part | Symbol / footprint | 3D model |
|---|---|---|
| SX1255 | own; land pattern per datasheet Rev. 3.1 figure 7-2, 9 thermal vias as a cross and 4 square paste openings (57 %) added | KiCad library `QFN-32-1EP_5x5mm_P0.5mm_EP3.3x3.3mm` (referenced) |
| LFCN-490+ | own; pads from the suggested layout PL-137 in the datasheet | `scripts/make_3d_models.py` |
| EVQ-Q2Y03W | own; land pattern checked against the Panasonic catalog ANCTB12E (pads 3.2 × 1.0 mm, 3.6 mm gap, 4.0 mm row pitch; pads in one row connected internally) | `scripts/make_3d_models.py` |
| SMA_Kinghelm_KH-SMA-KE-Z_Vertical | own; from the Kinghelm drawing (2019-06-06), drills enlarged for the JLCPCB tolerance, antipads on In1/In2 | `scripts/make_3d_models.py` |
| TA1651A | own symbol (pins after the datasheet: 2 (B) = IN, 5 (E) = OUT, 1/3/4/6 (A, C, D, F) = GND, names `IN`/`OUT`/`GND`); footprint per datasheet Rev. 1 section E (pad 1 wide, top left; the same land pattern as the former SF2446E, so the layout did not change) | `scripts/make_3d_models.py` (ceramic height and lid assumed, 1.35 mm overall, 1.4 mm max.) |
| Logo (`G***`) | Phenix-1255 project logo (own, also used in Phenix-1255-HW and phenix-1255-sw) | – |
| TG2016SMN | own footprint per datasheet TG2016/2520SMN_EN ver. 1.3 section 8 (pads 0.6 × 0.75 mm, pitch 1.65 × 1.13 mm), drawn with the long side vertical like the KiCad TG2520SMN footprint (pin 1 top left), with the same keepout between the pads; symbol `Oscillator:TG2520SMN-xx.xxxxxxMhz-xxxxNM` from the KiCad library (same pinout) | `scripts/make_3d_models.py` (lid height assumed) |
| Display_128x64_096_I2C | footprint by TG9541 (github.com/TG9541/kicad-footprints, CC0), own symbol | own (`Display_128x64_096_I2C.stp`, also contributed to Phenix-1255-HW) |

- The project is licensed under CERN-OHL-P-2.0 (`LICENSE`); third-party content is listed in the README.
- Phenix-1255-HW (Copyright © Z32IT 2026) is also CERN-OHL-P-2.0. The licence requires keeping its notice and marking changes with a date: keep the README sections *Changes from Phenix-1255-HW* and *License* up to date when the design departs further from the original.
- License notices in the files: the title blocks of both schematic sheets and of the PCB (revision `V2`, date, Z32IT, w4tchd0g (DM5LF), CERN-OHL-P-2.0, source URL), and an SPDX header (`SPDX-FileCopyrightText` / `SPDX-License-Identifier: CERN-OHL-P-2.0`) after the shebang of every script. Give new scripts the same header.
- The SX1255 and EVQ-Q2Y03W symbols use the pin names `VBATI`, `VR_ANAI` and `GND_n`. All pins are `passive`.
- The filter symbols (LFCN-490+, TA1651A) are compact 10.16 × 7.62 mm boxes with the IEC 60617 filter glyph (three waves, low frequency at the bottom; low-pass: upper two crossed out, band-pass: upper and lower crossed out). Pin names and numbers are hidden. The GND pins are stacked at the bottom centre (one visible, the others hidden at the same position). FL1 and FL2 are placed mirrored (`mirror y`) so that the signal runs from right to left.
- `scripts/make_3d_models.py` needs build123d (`pip install build123d`, Python ≤ 3.13). It writes `LFCN-490+.step`, `EVQ-Q2Y03W.step`, `KH-SMA-KE-Z.step`, `TA1651A.step` and `TG2016SMN.step`. Run single models with `python3 -c 'import make_3d_models as m; m.kh_sma_ke_z()'` from `scripts/`, so the other STEP files stay unchanged.

To add a part:

1. Put the symbol in `ext_parts/<Part>.kicad_sym` and the footprint in `ext_parts/<Part>.pretty/`.
2. Put the 3D model in `ext_parts/3d/` and link it as `${KIPRJMOD}/ext_parts/3d/<file>`. Prefer referencing KiCad library models via `${KICAD10_3DMODEL_DIR}` over copying them.
3. Register the libraries in `sym-lib-table` / `fp-lib-table`.
4. Keep manufacturer downloads and datasheets in `ext_parts/source/`. That folder is ignored by git: datasheets and vendor libraries (SamacSys, Ultra Librarian, SnapEDA, …) are usually not redistributable. Link the datasheet in the `Datasheet` field instead.
5. Do not commit vendor library files. Draw symbols and footprints from the datasheet, or use libraries with an open license (KiCad library: CC-BY-SA 4.0, attribute in the README).

## Repository housekeeping

- `.history/` is KiCad's local history and is ignored.
