import bcrypt

sifre = "admin123"   # burada istediğin şifre
hashed = bcrypt.hashpw(sifre.encode(), bcrypt.gensalt())
print(hashed.decode())
