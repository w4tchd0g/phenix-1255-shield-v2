#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 w4tchd0g (DM5LF)
# SPDX-License-Identifier: CERN-OHL-P-2.0
"""Helper for assembly.sh: converts KiCad BOM and position exports to the JLCPCB format.

Usage: jlc_csv.py BOM_IN POS_IN BOM_OUT CPL_OUT

BOM_IN:  ungrouped `kicad-cli sch export bom` with the columns
         Reference, Value, Footprint, MPN, LCSC (DNP parts excluded).
POS_IN:  `kicad-cli pcb export pos --format csv --units mm` (DNP parts excluded).
BOM_OUT: Comment, Designator, Footprint, LCSC Part #
CPL_OUT: Designator, Mid X, Mid Y, Layer, Rotation
"""
import csv
import re
import sys

# JLCPCB counts the rotation from the orientation of the part in its own library,
# which differs from the KiCad footprint for some packages. These offsets are added
# to the KiCad rotation (top side). They are the values commonly used for KiCad
# library footprints (pin 1 at the top left); the SX1255 footprint has the same
# pin 1 position as the KiCad QFN footprints. Check the placement preview in the
# JLCPCB order and adjust here if a part shows up rotated.
ROTATION_OFFSET = [
    (r"^SOT-23", 180),  # SOT-23, SOT-23-5, SOT-23-6
    (r"^QFN50P500X500X80-33N", 270),  # SX1255, QFN-32
]

# For these reference prefixes the value is the meaningful comment; all other
# parts are described by their manufacturer part number.
VALUE_PREFIXES = ("C", "R", "L")


def natural(ref):
    m = re.match(r"([A-Za-z]+)(\d+)", ref)
    return (m.group(1), int(m.group(2))) if m else (ref, 0)


def prefix(ref):
    return re.match(r"[A-Za-z]+", ref).group(0)


def read_bom(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def read_pos(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main():
    bom_in, pos_in, bom_out, cpl_out = sys.argv[1:5]
    bom = read_bom(bom_in)
    pos = read_pos(pos_in)

    bom_refs = {r["Reference"] for r in bom}
    pos_refs = {r["Ref"] for r in pos}
    if bom_refs != pos_refs:
        only_bom = sorted(bom_refs - pos_refs, key=natural)
        only_pos = sorted(pos_refs - bom_refs, key=natural)
        sys.exit(
            "BOM and position file differ (check the DNP flags in schematic and PCB):\n"
            f"  only in the schematic BOM: {', '.join(only_bom) or '-'}\n"
            f"  only in the PCB position file: {', '.join(only_pos) or '-'}"
        )

    # BOM: one row per part type.
    groups = {}
    for r in bom:
        ref = r["Reference"]
        footprint = r["Footprint"].split(":")[-1]
        if prefix(ref) in VALUE_PREFIXES or not r["MPN"]:
            comment = r["Value"]
        else:
            comment = r["MPN"]
        key = (comment, footprint, r["LCSC"])
        groups.setdefault(key, []).append(ref)

    rows = sorted(groups.items(), key=lambda kv: natural(min(kv[1], key=natural)))
    with open(bom_out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, quoting=csv.QUOTE_ALL)
        w.writerow(["Comment", "Designator", "Footprint", "LCSC Part #"])
        for (comment, footprint, lcsc), refs in rows:
            w.writerow([comment, ",".join(sorted(refs, key=natural)), footprint, lcsc])

    # CPL: one row per part.
    corrected = []
    with open(cpl_out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, quoting=csv.QUOTE_ALL)
        w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
        for r in sorted(pos, key=lambda r: natural(r["Ref"])):
            rot = float(r["Rot"])
            for pattern, offset in ROTATION_OFFSET:
                if re.search(pattern, r["Package"]):
                    rot += offset
                    corrected.append(f"{r['Ref']} (+{offset}°)")
                    break
            layer = "Top" if r["Side"] == "top" else "Bottom"
            w.writerow(
                [r["Ref"], f"{float(r['PosX']):.4f}mm", f"{float(r['PosY']):.4f}mm", layer, f"{rot % 360:g}"]
            )

    missing = sorted((r["Reference"] for r in bom if not r["LCSC"]), key=natural)
    print(f"{len(bom)} parts in {len(rows)} BOM lines")
    print(f"Rotation offset applied: {', '.join(corrected) or '-'}")
    if missing:
        print(f"WARNING: no LCSC part number: {', '.join(missing)}")


if __name__ == "__main__":
    main()
