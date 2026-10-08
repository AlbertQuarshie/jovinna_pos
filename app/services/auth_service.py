"""User accounts and login. Passwords are stored as salted PBKDF2 hashes, never as plain text."""
import hashlib
import hmac
import secrets

from sqlalchemy import func, select

from app.db.database import SessionLocal
from app.db.models import User

ROLES = ("admin", "cashier")
_ITERATIONS = 200_000
MIN_PASSWORD_LEN = 4


class AuthError(Exception):
    pass


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), _ITERATIONS).hex()
    return f"pbkdf2_sha256${_ITERATIONS}${salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, iterations, salt, digest = stored.split("$")
    except ValueError:
        return False
    check = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iterations)).hex()
    return hmac.compare_digest(check, digest)


def has_users() -> bool:
    with SessionLocal() as session:
        return session.scalar(select(User.id).limit(1)) is not None


def authenticate(username: str, password: str) -> User:
    with SessionLocal() as session:
        user = session.scalar(select(User).where(func.lower(User.username) == username.strip().lower()))
    if user is None or not verify_password(password, user.password_hash):
        raise AuthError("Wrong username or password.")
    if not user.is_active:
        raise AuthError("This account has been disabled. Ask the admin.")
    return user


def list_users() -> list[User]:
    with SessionLocal() as session:
        return list(session.scalars(select(User).order_by(User.role, User.full_name)))


def _check_password(password: str) -> None:
    if len(password) < MIN_PASSWORD_LEN:
        raise AuthError(f"Password must be at least {MIN_PASSWORD_LEN} characters.")


def create_user(username: str, full_name: str, password: str, role: str) -> User:
    username, full_name = username.strip().lower(), full_name.strip()
    if not username or not full_name:
        raise AuthError("Username and full name are required.")
    if role not in ROLES:
        raise AuthError(f"Role must be one of: {', '.join(ROLES)}.")
    _check_password(password)
    with SessionLocal() as session, session.begin():
        if session.scalar(select(User.id).where(func.lower(User.username) == username)):
            raise AuthError(f"Username '{username}' is already taken.")
        user = User(username=username, full_name=full_name, role=role, password_hash=hash_password(password))
        session.add(user)
    return user


def _active_admin_count(session) -> int:
    return session.scalar(select(func.count(User.id)).where(User.role == "admin", User.is_active.is_(True)))


def update_user(user_id: int, *, full_name: str, role: str, is_active: bool) -> None:
    if role not in ROLES:
        raise AuthError(f"Role must be one of: {', '.join(ROLES)}.")
    with SessionLocal() as session, session.begin():
        user = session.get(User, user_id)
        losing_admin = user.role == "admin" and user.is_active and (role != "admin" or not is_active)
        if losing_admin and _active_admin_count(session) <= 1:
            raise AuthError("There must always be at least one active admin.")
        user.full_name = full_name.strip() or user.full_name
        user.role = role
        user.is_active = is_active


def set_password(user_id: int, password: str) -> None:
    _check_password(password)
    with SessionLocal() as session, session.begin():
        session.get(User, user_id).password_hash = hash_password(password)
