
from argon2 import PasswordHasher, verify_password


def hash_password (password):
    return PasswordHasher(password)

def verify_password_hash(password,password_hash):
    return verify_password(password,password_hash)
