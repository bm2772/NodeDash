"""Auth primitives with zero native dependencies:
   - PBKDF2-HMAC-SHA256 password hashing (stdlib hashlib)
   - HS256 JWT sign/verify (stdlib hmac + hashlib)
"""
import base64
import hashlib
import hmac
import json
import os
import time
from typing import Optional

_PBKDF2_ROUNDS = 200_000


# --------------------------------------------------------------------------- #
# Password hashing
# --------------------------------------------------------------------------- #
def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _PBKDF2_ROUNDS)
    return f"{salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, dk_hex = stored.split("$", 1)
        dk = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt_hex), _PBKDF2_ROUNDS
        )
        return hmac.compare_digest(dk.hex(), dk_hex)
    except Exception:
        return False


# --------------------------------------------------------------------------- #
# JWT (HS256)
# --------------------------------------------------------------------------- #
def _b64u(raw: bytes) -> bytes:
    return base64.urlsafe_b64encode(raw).rstrip(b"=")


def _b64u_decode(seg: str) -> bytes:
    return base64.urlsafe_b64decode(seg + "=" * (-len(seg) % 4))


def create_token(payload: dict, secret: str, exp_seconds: int) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    body = dict(payload)
    body["exp"] = int(time.time()) + exp_seconds
    signing_input = (
        _b64u(json.dumps(header, separators=(",", ":")).encode())
        + b"."
        + _b64u(json.dumps(body, separators=(",", ":")).encode())
    )
    sig = hmac.new(secret.encode(), signing_input, hashlib.sha256).digest()
    return (signing_input + b"." + _b64u(sig)).decode()


def decode_token(token: str, secret: str) -> Optional[dict]:
    try:
        signing_input, sig_b64 = token.rsplit(".", 1)
        expected = hmac.new(
            secret.encode(), signing_input.encode(), hashlib.sha256
        ).digest()
        if not hmac.compare_digest(_b64u(expected).decode(), sig_b64):
            return None
        _, body_b64 = signing_input.split(".")
        body = json.loads(_b64u_decode(body_b64))
        if int(body.get("exp", 0)) < int(time.time()):
            return None
        return body
    except Exception:
        return None
