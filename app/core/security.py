
from argon2 import PasswordHasher

hasher = PasswordHasher()
def hash_password (password:str)->str:
    return hasher.hash(password)

def verify_password_hash(password,password_hash):
    return hasher.verify(password,password_hash)
