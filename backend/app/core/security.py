"""Security helpers: Fernet token cipher, OAuth state hashing, PKCE."""

from __future__ import annotations

import base64
import hashlib
import secrets

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings


class TokenCipherError(RuntimeError):
    """Raised when encryption configuration is missing or ciphertext is invalid."""


class TokenCipher:
    """Encrypt/decrypt provider access tokens with Fernet (authenticated encryption)."""

    def __init__(self, key: str | None = None) -> None:
        resolved = key if key is not None else get_settings().token_encryption_key
        if not resolved:
            raise TokenCipherError(
                "TOKEN_ENCRYPTION_KEY is not configured. "
                "Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
            )
        try:
            self._fernet = Fernet(resolved.encode("utf-8") if isinstance(resolved, str) else resolved)
        except Exception as exc:  # noqa: BLE001 — invalid key format
            raise TokenCipherError("TOKEN_ENCRYPTION_KEY is invalid.") from exc

    def encrypt(self, token: str) -> str:
        """Return Fernet ciphertext as a UTF-8 string suitable for DB storage."""
        return self._fernet.encrypt(token.encode("utf-8")).decode("utf-8")

    def decrypt(self, ciphertext: str) -> str:
        """Decrypt Fernet ciphertext back to the original token string."""
        try:
            return self._fernet.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
        except InvalidToken as exc:
            raise TokenCipherError("Unable to decrypt token.") from exc


def generate_oauth_state() -> str:
    """Cryptographically random OAuth state (URL-safe)."""
    return secrets.token_urlsafe(32)


def hash_oauth_state(state: str) -> str:
    """SHA-256 hex digest of OAuth state for DB storage."""
    return hashlib.sha256(state.encode("utf-8")).hexdigest()


def generate_pkce_pair() -> tuple[str, str]:
    """Return (code_verifier, code_challenge) using S256."""
    # High-entropy verifier (43–128 chars of URL-safe text).
    code_verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return code_verifier, code_challenge
