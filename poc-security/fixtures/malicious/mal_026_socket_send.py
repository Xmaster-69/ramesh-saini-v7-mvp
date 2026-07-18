import socket
s = socket.socket()
s.connect(("10.0.0.1", 9000))
s.send(b"confidential")