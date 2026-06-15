import hashlib

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


def hash_ssn(ssn: str) -> str:
    """SHA-256 hex digest of the canonical 9-digit SSN.

    Stored alongside ssn_encrypted to allow duplicate detection without
    decryption. Fernet uses a random IV so the same SSN produces different
    ciphertext each time — this hash is the only dedup-able representation.
    """
    return hashlib.sha256(ssn.encode()).hexdigest()
