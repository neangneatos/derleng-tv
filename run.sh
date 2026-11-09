#!/bin/bash
# Optional external bot worker. The Mini App itself runs on Hostinger.
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"
if [ ! -f .env ]; then
  echo "Missing private .env for the optional bot worker." >&2
  exit 1
fi
if [ ! -f "${DERLENG_CATALOG_FILE:-dist/hostinger/channels_public.json}" ]; then
  echo "Build the release first: python3 build_release.py" >&2
  exit 1
fi
exec python3 bot.py
