#!/usr/bin/env bash
# Mac/Linux — op Windows gebruik start.bat
set -e
cd "$(dirname "$0")"
echo "→ Eneco Heat Dashboard starten..."
echo ""
if ! command -v node &>/dev/null; then
  echo "❌ Node.js niet gevonden. Installeer via https://nodejs.org"
  exit 1
fi
npm install
echo ""
echo "✓ Browser opent op http://localhost:5173/"
echo "  Stoppen met Ctrl+C"
echo ""
npm run dev
