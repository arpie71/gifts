#!/usr/bin/env bash
# Rebuild the revised analysis from the original analysis file and Wikidata caches.
# Usage (from the repo root):  bash analysis_revised/run_all.sh [--fetch]
#   --fetch   also refresh the Wikidata caches (network access; otherwise the committed caches are used)
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
PY="${PY:-/home/arpie/envs/revised/bin/python}"
cd "$REPO"
mkdir -p analysis_revised/logs
# Earlier builds are renamed into archive/, never deleted.
STAMP=$(date +%Y%m%d_%H%M%S)
for d in data output; do
  if [[ -d analysis_revised/$d ]]; then
    mkdir -p analysis_revised/archive
    mv analysis_revised/$d analysis_revised/archive/${d}_$STAMP
  fi
done
mkdir -p analysis_revised/data analysis_revised/output/tables analysis_revised/output/figures
if [[ "${1:-}" == "--fetch" ]]; then
  "$PY" -u analysis_revised/01b_fetch_missing_claims.py | tee analysis_revised/logs/01b_fetch.log
  "$PY" -u analysis_revised/01_fetch_position_metadata.py | tee analysis_revised/logs/01_fetch.log
fi
"$PY" -u analysis_revised/02_build_data.py  > analysis_revised/logs/02_build.log 2>&1
"$PY" -u analysis_revised/03_models.py      > analysis_revised/logs/03_models.log 2>&1
"$PY" -u analysis_revised/04_figures.py     > analysis_revised/logs/04_figures.log 2>&1
"$PY" -u analysis_revised/05_codebook.py    > analysis_revised/logs/05_codebook.log 2>&1
sha256sum analysis_revised/data/*.csv analysis_revised/output/tables/*.csv > analysis_revised/logs/checksums.txt
echo "done; see analysis_revised/logs/"
