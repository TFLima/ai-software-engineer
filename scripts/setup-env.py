#!/usr/bin/env python3
"""Generate local-only credentials without printing or overwriting them."""
import argparse
import base64
import os
from pathlib import Path
import secrets

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--add-internal-secret", action="store_true",
                    help="Add the B04 secret to an existing .env without changing existing values")
args = parser.parse_args()

root = Path(__file__).resolve().parent.parent
destination = root / ".env"
if args.add_internal_secret:
    if not destination.is_file():
        raise SystemExit(".env does not exist; run setup-env.py without options first.")
    existing = destination.read_text()
    if any(line.startswith("AI_INTERNAL_SECRET=") for line in existing.splitlines()):
        raise SystemExit("AI_INTERNAL_SECRET already exists; preserved without changes.")
    with destination.open("a") as stream:
        stream.write("\nAI_INTERNAL_SECRET=" + secrets.token_hex(32) + "\n")
    destination.chmod(0o600)
    print("Added the local internal secret without changing existing credentials.")
    raise SystemExit(0)

content = (
    "# Local B02 credentials. Do not commit.\n"
    f"APP_KEY=base64:{base64.b64encode(secrets.token_bytes(32)).decode()}\n"
    f"DB_PASSWORD={secrets.token_hex(32)}\n"
    f"AI_INTERNAL_SECRET={secrets.token_hex(32)}\n"
)
try:
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
except FileExistsError:
    raise SystemExit(".env already exists; preserved without changes.")
with os.fdopen(descriptor, "w") as stream:
    stream.write(content)
print("Created local .env with mode 0600.")
