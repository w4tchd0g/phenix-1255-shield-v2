#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 w4tchd0g (DM5LF)
# SPDX-License-Identifier: CERN-OHL-P-2.0
# Exports the BOM and the position file (CPL) for JLCPCB assembly.
# Parts marked "Do not populate" are left out of both files.
# Usage: ./scripts/assembly.sh   (run from anywhere)
# Output: production/phenix-1255-shield-v2-bom.csv and production/phenix-1255-shield-v2-cpl.csv
set -euo pipefail

cd "$(dirname "$0")/.."

KICAD_CLI="${KICAD_CLI:-$(command -v kicad-cli || echo /Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli)}"
P=phenix-1255-shield-v2
BOM=production/$P-bom.csv
CPL=production/$P-cpl.csv

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
mkdir -p production

# Schematic: one row per part, DNP parts excluded. jlc_csv.py does the grouping.
"$KICAD_CLI" sch export bom -o "$TMP/bom.csv" --exclude-dnp \
  --fields 'Reference,Value,Footprint,MPN,LCSC' --labels 'Reference,Value,Footprint,MPN,LCSC' \
  --group-by '' --ref-range-delimiter '' "$P.kicad_sch" >/dev/null

# PCB: absolute coordinates like the Gerber and drill files, DNP parts excluded.
"$KICAD_CLI" pcb export pos -o "$TMP/pos.csv" --format csv --units mm --side both \
  --exclude-dnp "$P.kicad_pcb" >/dev/null

python3 scripts/jlc_csv.py "$TMP/bom.csv" "$TMP/pos.csv" "$BOM" "$CPL"

echo "Created $BOM and $CPL"
