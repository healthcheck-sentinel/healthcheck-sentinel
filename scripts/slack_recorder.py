"""Local HTTP webhook capture for demos. This does not contact Slack."""
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from datetime import datetime, timezone

messages = []

class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        messages.append({'received_at': datetime.now(timezone.utc).isoformat(), 'payload': payload})
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'ok')

    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(messages).encode())

    def log_message(self, *args):
        pass

HTTPServer(('0.0.0.0', 8080), Handler).serve_forever()
