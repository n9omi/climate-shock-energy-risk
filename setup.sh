#!/usr/bin/env bash
# setup.sh | One-time setup: a virtual environment with every package, the regime-risk models this project
# builds on, and a headless browser for the PDF report and dashboard screenshots (skipped if Chrome or Edge is installed).
# Needs Python 3.11+. To pick a specific one: PYTHON=python3.12 bash setup.sh
set -euo pipefail
cd "$(dirname "$0")"
"${PYTHON:-python3}" -m venv .venv
.venv/bin/python -m pip install --upgrade pip -q
.venv/bin/python -m pip install -r requirements.txt -q

# The models come from github.com/n9omi/regime-risk-and-model-validation, installed as the package `regime_risk`.
# A copy in the folder next to this one wins (handy while you edit both); otherwise it is installed from GitHub.
if [[ -f ../regime-risk-and-model-validation/pyproject.toml ]]; then
  echo "Installing regime_risk from ../regime-risk-and-model-validation (editable)"
  .venv/bin/python -m pip install -q -e ../regime-risk-and-model-validation
else
  echo "Installing regime_risk from GitHub"
  .venv/bin/python -m pip install -q "regime-risk @ git+https://github.com/n9omi/regime-risk-and-model-validation.git"
fi

if [[ ! -d "/Applications/Google Chrome.app" && ! -d "/Applications/Microsoft Edge.app" ]] \
   && ! command -v google-chrome >/dev/null 2>&1; then
  echo "No Chrome/Edge found: installing Playwright's Chromium (~150 MB, once)"
  .venv/bin/python -m playwright install chromium
fi
echo "Setup complete. Next: bash run.sh"
