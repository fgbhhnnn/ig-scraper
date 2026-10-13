"""Build helper: download cv-cat/TiktokApis signing/pure.py at the pinned commit, verify SHA-256,
and place it in build_vendor/tiktok_sign/pure.py for PyInstaller to bundle. Not committed to the repo."""
import hashlib, os, sys, urllib.request
COMMIT = 'b3b2a448800e4ca9e061203b9ba1f53d1d6d3082'
URL = f'https://raw.githubusercontent.com/cv-cat/TiktokApis/{COMMIT}/signing/pure.py'
SHA256 = '74326dada4b64cfadd466a39e514eacd8eaa53fa2f9af3c14f771ae8d16c067d'
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'build_vendor', 'tiktok_sign', 'pure.py')
data = urllib.request.urlopen(URL, timeout=60).read()
h = hashlib.sha256(data).hexdigest()
if h != SHA256:
    print(f'SHA-256 MISMATCH: got {h}, expected {SHA256}'); sys.exit(1)
os.makedirs(os.path.dirname(out), exist_ok=True)
open(out, 'wb').write(data)
print(f'TikTok signer SHA-256 OK: {h} ({len(data)} bytes, commit {COMMIT[:7]})')
