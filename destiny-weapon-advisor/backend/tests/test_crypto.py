from app.crypto import encrypt, decrypt, generate_key


def test_round_trip():
    key = generate_key()
    ct = encrypt("super-secret-token", key)
    assert isinstance(ct, bytes)
    assert ct != b"super-secret-token"
    assert decrypt(ct, key) == "super-secret-token"


def test_wrong_key_fails():
    import pytest
    from cryptography.fernet import InvalidToken
    ct = encrypt("x", generate_key())
    with pytest.raises(InvalidToken):
        decrypt(ct, generate_key())
