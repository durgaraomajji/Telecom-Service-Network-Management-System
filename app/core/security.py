from datetime import datetime, timedelta, timezone
from jose import jwt, JWTError
from pwdlib import PasswordHash
from app.core.config import settings

_password_hash = PasswordHash.recommended()

def hash_password(password: str) -> str:
    return _password_hash.hash(password)

def verify_password(password: str, hashed: str) -> bool:
    return _password_hash.verify(password, hashed)

def create_token(subject: str, token_type: str = "access", expires_minutes: int | None = None) -> str:
    now = datetime.now(timezone.utc)
    expiry = now + (timedelta(minutes=expires_minutes) if expires_minutes else
                    (timedelta(days=settings.refresh_token_expire_days) if token_type == "refresh"
                     else timedelta(minutes=settings.access_token_expire_minutes)))
    return jwt.encode({"sub": subject, "type": token_type, "iat": now, "exp": expiry},
                      settings.secret_key, algorithm=settings.algorithm)

def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    except JWTError as exc:
        raise ValueError("Invalid or expired token") from exc
