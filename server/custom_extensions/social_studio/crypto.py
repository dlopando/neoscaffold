"""Authenticated encryption for OAuth tokens at rest.

Ciphertext format (version 1)::

    urlsafe-base64( nonce[16] || hmac-sha256[32] || xor-ciphertext )

The keystream is SHA-256 in counter mode keyed by
``SHA-256(b"social-studio-v1\\0" + SOCIAL_STUDIO_SECRET_KEY)``.
The HMAC covers the nonce and ciphertext. Tokens are never logged by
this module, and the ciphertext does not contain the plaintext.
"""

import base64
import hashlib
import hmac
import os

_VERSION = b"social-studio-v1\0"
_NONCE_LEN = 16
_MAC_LEN = 32


class CryptoError(RuntimeError):
    """Token encryption failed or the ciphertext is not authentic."""


def secret_key(env=None):
    source = os.environ if env is None else env
    value = str(source.get("SOCIAL_STUDIO_SECRET_KEY") or "").strip()
    if not value:
        raise CryptoError(
            "SOCIAL_STUDIO_SECRET_KEY is not set. "
            "Refusing to store social tokens in plaintext."
        )
    return value


def _master_key(secret):
    return hashlib.sha256(_VERSION + secret.encode("utf-8")).digest()


def _keystream(key, nonce, length):
    chunks = []
    counter = 0
    produced = 0
    while produced < length:
        block = hashlib.sha256(
            key + nonce + counter.to_bytes(4, "big")
        ).digest()
        chunks.append(block)
        produced += len(block)
        counter += 1
    return b"".join(chunks)[:length]


def encrypt(plaintext, env=None):
    """Encrypt a token string. Returns URL-safe base64 ciphertext."""
    if plaintext is None:
        plaintext = ""
    if not isinstance(plaintext, str):
        plaintext = str(plaintext)
    secret = secret_key(env)
    key = _master_key(secret)
    nonce = os.urandom(_NONCE_LEN)
    raw = plaintext.encode("utf-8")
    stream = _keystream(key, nonce, len(raw))
    cipher = bytes(left ^ right for left, right in zip(raw, stream))
    mac = hmac.new(key, b"mac\0" + nonce + cipher, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(nonce + mac + cipher).decode("ascii")


def decrypt(blob, env=None):
    """Decrypt a token. Raises CryptoError if the key or MAC does not match."""
    if blob is None or blob == "":
        return ""
    secret = secret_key(env)
    try:
        raw = base64.urlsafe_b64decode(str(blob).encode("ascii"))
    except Exception as exc:
        raise CryptoError("token ciphertext is not valid base64") from exc
    if len(raw) < _NONCE_LEN + _MAC_LEN:
        raise CryptoError("token ciphertext is truncated")
    nonce = raw[:_NONCE_LEN]
    mac = raw[_NONCE_LEN : _NONCE_LEN + _MAC_LEN]
    cipher = raw[_NONCE_LEN + _MAC_LEN :]
    key = _master_key(secret)
    expected = hmac.new(key, b"mac\0" + nonce + cipher, hashlib.sha256).digest()
    if not hmac.compare_digest(mac, expected):
        raise CryptoError("token ciphertext failed authentication")
    stream = _keystream(key, nonce, len(cipher))
    plain = bytes(left ^ right for left, right in zip(cipher, stream))
    return plain.decode("utf-8")


def plaintext_in_ciphertext(plaintext, blob):
    """True when the secret string appears in the stored blob. Tests use this."""
    if not plaintext:
        return False
    return plaintext in str(blob or "")
