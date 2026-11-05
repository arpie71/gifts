#!/usr/bin/env bash
# Reproduce the ORIGINAL analysis (analysis/build_analysis_data.py + analysis/descriptives.py)
# in a scratch copy of the repo and compare every output with the committed files.
# Nothing in the repo is modified. The scratch tree's old outputs are renamed (*_prev),
# never deleted, before the rerun.
#
# Usage (from the repo root):  bash analysis_revised/00_reproduce_original.sh [scratch_dir]
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
PY="${PY:-/home/arpie/envs/revised/bin/python}"
SCR="${1:-/tmp/gifts_repro_$(date +%Y%m%d_%H%M%S)}"
LOG="$REPO/analysis_revised/logs/00_reproduce_original.log"

mkdir -p "$SCR"
cp -r "$REPO/xml" "$REPO/cleaned" "$REPO/files" "$REPO/analysis" "$REPO/paper" "$SCR/"
cd "$SCR"
for d in analysis/output paper/tables paper/figures; do
  mv "$d" "${d}_prev"; mkdir "$d"
done
{
  echo "Reproduction of the original analysis, $(date -Iseconds)"
  echo "scratch: $SCR   python: $($PY --version 2>&1)"
  "$PY" analysis/build_analysis_data.py > build.log 2>&1 && echo "build_analysis_data.py: ok"
  "$PY" analysis/descriptives.py > desc.log 2>&1 && echo "descriptives.py: ok"
  echo "--- comparison with committed outputs (SAME = byte-identical)"
  for f in analysis/output_prev/*; do b=$(basename "$f")
    cmp -s "$f" "analysis/output/$b" && echo "SAME analysis/output/$b" || echo "DIFF analysis/output/$b"; done
  for f in paper/tables_prev/*; do b=$(basename "$f")
    cmp -s "$f" "paper/tables/$b" && echo "SAME paper/tables/$b" || echo "DIFF paper/tables/$b"; done
  for f in paper/figures_prev/*; do b=$(basename "$f")
    cmp -s "$f" "paper/figures/$b" && echo "SAME paper/figures/$b" || echo "DIFF paper/figures/$b"; done
  echo "Note: PDF figures and the plotly HTML embed creation dates / random ids, so DIFF is expected for"
  echo "*.pdf and map_gifts_by_country.html; the PNG renderings of the same figures are compared byte-for-byte."
} | tee "$LOG"
