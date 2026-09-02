#!/usr/bin/env python3
"""mtp_notify — fire a cache-invalidation webhook at MineTerminal Pro.

Fire-and-forget: spawned in a daemon thread so the admin response is not
blocked by MTP's response. Bounded retry with short backoff. Failures are
logged to stderr and never raised.
"""
from __future__ import annotations
import hashlib
import hmac
import json
import sys
import threading
import time
import urllib.error
import urllib.request

_SECRET_FILE = "/opt/mineportal/.mtp_invalidate_secret"
_URL = "https://mineterminalpro.com/api/cache/invalidate"


def _secret() -> str:
    try:
        return open(_SECRET_FILE).read().strip()
    except Exception:
        return ""


def _post_once(payload: bytes, sig: str, timeout: float = 5.0):
    req = urllib.request.Request(
        _URL, data=payload, method="POST",
        headers={
            "Content-Type": "application/json",
            "X-MTP-Signature": sig,
            "User-Agent": "mineco-portal/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read(200).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        body = e.read(200).decode("utf-8", "replace") if e.fp else ""
        return e.code, body
    except Exception as e:
        return -1, repr(e)


def _send(kind: str, table=None, rid=None) -> None:
    secret = _secret()
    if not secret:
        return
    body = {
        "kind": kind,
        "table": table,
        "id": rid,
        "ts": int(time.time()),
    }
    payload = json.dumps(body, separators=(",", ":")).encode()
    sig = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    for attempt in range(3):
        code, _ = _post_once(payload, sig)
        if 200 <= code < 300:
            return
        time.sleep(0.5 * (attempt + 1))
    sys.stderr.write(f"[mtp_notify] gave up: kind={kind} table={table} id={rid}\n")


def notify(kind: str, table=None, rid=None) -> None:
    """Public entrypoint. Spawns a daemon thread; returns immediately."""
    try:
        t = threading.Thread(target=_send, args=(kind, table, rid), daemon=True)
        t.start()
    except Exception as e:
        sys.stderr.write(f"[mtp_notify] thread spawn failed: {e!r}\n")
