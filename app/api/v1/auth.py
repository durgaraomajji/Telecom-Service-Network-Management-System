from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from sqlalchemy import func, select
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import RegisterRequest, TokenResponse, UserResponse
from app.core.security import hash_password, verify_password, create_token, decode_token

router = APIRouter(prefix="/auth", tags=["Authentication"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")
oauth2_optional = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)
STAFF_ROLES = {"super_admin", "operations_manager", "support_agent", "network_engineer", "field_technician"}

def _optional_user(token: str | None, db: Session):
    """Return the logged-in user if a valid token was sent, else None."""
    if not token:
        return None
    try:
        claims = decode_token(token)
        user = db.get(User, int(claims["sub"]))
        if claims.get("type") == "access" and user and user.is_active:
            return user
    except (ValueError, KeyError, TypeError):
        pass
    raise HTTPException(401, "Invalid or expired access token",
                        headers={"WWW-Authenticate": "Bearer"})


@router.post("/register", response_model=UserResponse, status_code=201,
             summary="Register a user (customer, or staff role with a super_admin token)")
def register(payload: RegisterRequest, db: Session = Depends(get_db),
             token: str | None = Depends(oauth2_optional)):
    if payload.role in STAFF_ROLES:
        no_users_yet = db.scalar(select(func.count(User.id))) == 0
        actor = _optional_user(token, db)
        is_super_admin = actor is not None and actor.role == "super_admin"
        # Bootstrap: the very first account on an empty system may be super_admin.
        first_admin = no_users_yet and payload.role == "super_admin"
        if not (is_super_admin or first_admin):
            raise HTTPException(
                403,
                f"Creating a '{payload.role}' account requires a super_admin. "
                "Click Authorize and log in as super_admin first, then register again.")
    if db.scalar(select(User).where(User.email == payload.email)):
        raise HTTPException(409, "Email already registered")
    user = User(full_name=payload.full_name, email=payload.email,
                password_hash=hash_password(payload.password), role=payload.role)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user

@router.post("/login", response_model=TokenResponse)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == form.username))
    if not user or not verify_password(form.password, user.password_hash) or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    return TokenResponse(access_token=create_token(str(user.id)),
                         refresh_token=create_token(str(user.id), "refresh"))

@router.post("/refresh", response_model=TokenResponse)
def refresh(refresh_token: str, db: Session = Depends(get_db)):
    try:
        claims = decode_token(refresh_token)
        if claims.get("type") != "refresh":
            raise ValueError("Wrong token type")
        user = db.get(User, int(claims["sub"]))
        if not user or not user.is_active:
            raise ValueError("Inactive user")
    except (ValueError, KeyError, TypeError):
        raise HTTPException(401, "Invalid refresh token")
    return TokenResponse(access_token=create_token(str(user.id)),
                         refresh_token=create_token(str(user.id), "refresh"))

def current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    try:
        claims = decode_token(token)
        if claims.get("type") != "access":
            raise ValueError("Wrong token type")
        user = db.get(User, int(claims["sub"]))
        if not user or not user.is_active:
            raise ValueError("Inactive user")
        return user
    except (ValueError, KeyError, TypeError):
        raise HTTPException(401, "Invalid or expired access token",
                            headers={"WWW-Authenticate": "Bearer"})

@router.get("/me", response_model=UserResponse)
def me(user: User = Depends(current_user)):
    return user
