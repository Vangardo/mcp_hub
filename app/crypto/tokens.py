import base64
import hashlib
from cryptography.fernet import Fernet

from app.settings import settings


def _get_fernet() -> Fernet:
    key = settings.tokens_encryption_key.encode()
    key_hash = hashlib.sha256(key).digest()
    fernet_key = base64.urlsafe_b64encode(key_hash)
    return Fernet(fernet_key)


def encrypt_token(token: str) -> str:
    fernet = _get_fernet()
    encrypted = fernet.encrypt(token.encode())
    return encrypted.decode()


def decrypt_token(encrypted_token: str) -> str:
    fernet = _get_fernet()
    decrypted = fernet.decrypt(encrypted_token.encode())
    return decrypted.decode()
