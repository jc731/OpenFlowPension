from cryptography.fernet import Fernet
from app.config import settings


def get_fernet() -> Fernet:
    return Fernet(settings.encryption_key.encode())


def encrypt_ssn(ssn: str) -> bytes:
    return get_fernet().encrypt(ssn.encode())


def decrypt_ssn(ciphertext: bytes) -> str:
    return get_fernet().decrypt(ciphertext).decode()


def mask_ssn(ssn: str) -> str:
    return f"***-**-{ssn[-4:]}"
