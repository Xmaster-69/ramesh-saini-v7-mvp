import hashlib
h = hashlib.sha256(b"hello")
print(h.hexdigest())