import os
from pathlib import Path
from dotenv import load_dotenv, set_key

# Define base directory
BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables
dotenv_path = BASE_DIR / ".env"
load_dotenv(dotenv_path)

# Enforce directories existence
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
SECURE_STORAGE_DIR = DATA_DIR / "storage"
PAGE_IMAGES_DIR = DATA_DIR / "pages"
DB_PATH = DATA_DIR / "db.sqlite3"

for directory in [DATA_DIR, UPLOAD_DIR, SECURE_STORAGE_DIR, PAGE_IMAGES_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

# Generate and set secrets in .env if they don't exist
def ensure_env_secret(key_name: str, generator_fn) -> str:
    val = os.getenv(key_name)
    if not val:
        val = generator_fn()
        # Create .env if it doesn't exist
        if not dotenv_path.exists():
            dotenv_path.touch()
        try:
            set_key(str(dotenv_path), key_name, val)
        except Exception:
            # Fallback to in-memory if writing fails
            pass
        # Update os.environ so it's loaded
        os.environ[key_name] = val
    return val

def generate_fernet_key() -> str:
    from cryptography.fernet import Fernet
    return Fernet.generate_key().decode()

def generate_jwt_secret() -> str:
    import secrets
    return secrets.token_hex(32)

# Load or generate credentials
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
ENCRYPTION_KEY = ensure_env_secret("ENCRYPTION_KEY", generate_fernet_key)
JWT_SECRET = ensure_env_secret("JWT_SECRET", generate_jwt_secret)

# Security Limits
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".txt"}
JWT_EXPIRY_MINUTES = 15
