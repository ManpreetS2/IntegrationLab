"""Unit tests for PKCE and Fernet token encryption."""

from app.core.security import TokenCipher, generate_pkce_pair, hash_oauth_state


def test_pkce_challenge_is_s256_shape() -> None:
    verifier, challenge = generate_pkce_pair()
    assert len(verifier) >= 43
    assert "=" not in challenge
    assert challenge != verifier


def test_state_hash_is_deterministic() -> None:
    assert hash_oauth_state("abc") == hash_oauth_state("abc")
    assert hash_oauth_state("abc") != hash_oauth_state("xyz")


def test_token_cipher_round_trip() -> None:
    cipher = TokenCipher()
    plaintext = "gho_example_secret_token"
    ciphertext = cipher.encrypt(plaintext)
    assert ciphertext != plaintext
    assert cipher.decrypt(ciphertext) == plaintext
