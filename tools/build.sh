#!/bin/sh
# Local build: fetch + verify the TikTok signer, then build the single-file exe.
set -e
cd "$(dirname "$0")/.."
python tools/fetch_signer.py
pyinstaller --noconfirm ig-scraper.spec
