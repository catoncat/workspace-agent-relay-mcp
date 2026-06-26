#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/frontend"
if command -v vp >/dev/null 2>&1; then
  vp install
  vp build
else
  npm install
  npm run build
fi
