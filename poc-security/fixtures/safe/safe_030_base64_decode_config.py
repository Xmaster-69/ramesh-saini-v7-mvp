import base64
encoded = "aGVsbG8="
decoded = base64.b64decode(encoded)
print(decoded)