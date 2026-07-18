import http.server
import socketserver
# Creating a local development server
handler = http.server.SimpleHTTPRequestHandler
with socketserver.TCPServer(("", 8000), handler) as httpd:
    print("Serving at port 8000")