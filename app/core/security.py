
from argon2 import PasswordHasher

hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return hasher.hash(password)


def verify_password_hash(password: str, password_hash: str) -> bool:
    return hasher.verify(password_hash, password)
