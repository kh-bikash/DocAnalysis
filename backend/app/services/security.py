import time
import hmac
import hashlib
import jwt
from typing import Optional, Tuple
from cryptography.fernet import Fernet
from backend.app.config import ENCRYPTION_KEY, JWT_SECRET, JWT_EXPIRY_MINUTES

# Initialize Fernet cipher for encryption/decryption at rest
# ENCRYPTION_KEY must be a 32-byte url-safe base64-encoded key
_cipher = Fernet(ENCRYPTION_KEY.encode() if isinstance(ENCRYPTION_KEY, str) else ENCRYPTION_KEY)

def encrypt_data(data: bytes) -> bytes:
    """Encrypt byte data using AES-256 Fernet."""
    return _cipher.encrypt(data)

def decrypt_data(data: bytes) -> bytes:
    """Decrypt byte data using AES-256 Fernet."""
    return _cipher.decrypt(data)

def sanitize_filename(filename: str) -> str:
    """Sanitize the original filename to prevent path traversal."""
    import re
    # Remove any directory separators or path manipulation sequences
    clean = re.sub(r'[\\/*?:|"<>..]', '', filename)
    # Ensure it's not empty, otherwise default
    if not clean or clean == '..':
        clean = "uploaded_file"
    return clean

def generate_page_token(document_id: str, page_number: int) -> str:
    """Generate a JWT token for securing page/thumbnail image access (expiring in 15m)."""
    payload = {
        "doc_id": document_id,
        "page": page_number,
        "exp": int(time.time()) + (JWT_EXPIRY_MINUTES * 60)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")

def validate_page_token(token: str, document_id: str, page_number: int) -> bool:
    """Validate a JWT token for accessing a specific document page."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        if payload.get("doc_id") != document_id:
            return False
        if payload.get("page") != page_number:
            return False
        return True
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return False
