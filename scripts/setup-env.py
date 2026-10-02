#!/usr/bin/env python3
"""Generate local-only credentials without printing or overwriting them."""
import base64
import os
from pathlib import Path
import secrets

root = Path(__file__).resolve().parent.parent
destination = root / ".env"
content = (
    "# Local B02 credentials. Do not commit.\n"
    f"APP_KEY=base64:{base64.b64encode(secrets.token_bytes(32)).decode()}\n"
    f"DB_PASSWORD={secrets.token_hex(32)}\n"
)
try:
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
except FileExistsError:
    raise SystemExit(".env already exists; preserved without changes.")
with os.fdopen(descriptor, "w") as stream:
    stream.write(content)
print("Created local .env with mode 0600.")
