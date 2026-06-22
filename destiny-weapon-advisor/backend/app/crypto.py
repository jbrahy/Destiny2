from cryptography.fernet import Fernet


def generate_key() -> str:
    return Fernet.generate_key().decode()


def encrypt(plaintext: str, key: str) -> bytes:
    return Fernet(key.encode()).encrypt(plaintext.encode())


def decrypt(token: bytes, key: str) -> str:
    return Fernet(key.encode()).decrypt(token).decode()
