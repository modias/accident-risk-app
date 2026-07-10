#!/usr/bin/env bash
set -euo pipefail

export PATH="/Users/amodi/.local/bin:$PATH"
REPO="modias/accident-risk-app"
APP_DIR="/Users/amodi/accident-risk-app"

cd "$APP_DIR"

if ! gh auth status >/dev/null 2>&1; then
  echo "GitHub login required. Complete the browser step when prompted."
  gh auth login --hostname github.com --git-protocol https --web
fi

if ! gh repo view "$REPO" >/dev/null 2>&1; then
  echo "Creating GitHub repository $REPO ..."
  gh repo create accident-risk-app --public --source=. --remote=origin --push
else
  git remote remove origin 2>/dev/null || true
  git remote add origin "https://github.com/$REPO.git"
  git push -u origin main
fi

echo ""
echo "Done. Deploy on Streamlit Community Cloud:"
echo "  1. Open https://share.streamlit.io"
echo "  2. New app -> $REPO"
echo "  3. Branch: main"
echo "  4. Main file: app.py"
