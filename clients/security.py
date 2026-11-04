import hashlib
from cryptography.fernet import Fernet
from django.conf import settings

def _fernet():
    return Fernet(settings.FIELD_KEY.encode())

def encrypt(text):
    return _fernet().encrypt(text.encode())

def decrypt(blob):
    return _fernet().decrypt(bytes(blob)).decode()

def sha256(text):
    return hashlib.sha256(text.strip().upper().encode()).hexdigest()