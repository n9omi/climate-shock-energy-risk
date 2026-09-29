#!/usr/bin/env bash
# run.sh | The whole study: prices and events, event study, regimes, VaR and the overlay, stress tests,
# then the PDF report, the dashboard and its screenshots, and the tests. About two minutes.
# Usage:  bash run.sh
set -euo pipefail
cd "$(dirname "$0")"
PY="${PYTHON:-python3}"
[ -x .venv/bin/python ] && PY=".venv/bin/python"

step() { echo; echo "=== $*"; "$PY" "$@"; }
for s in pipeline/0[1-5]_*.py; do step "$s"; done
step make_report.py
step make_dashboard.py
echo; echo "=== tests"; "$PY" -m pytest -q tests
echo; echo "Done. Report: reports/climate_shock_energy_risk_report.pdf · Dashboard: docs/index.html"
