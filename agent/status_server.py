"""Read-only local demo status endpoint; never accepts operational commands."""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread


def start_status_server(agent, port):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path != '/status':
                self.send_error(404)
                return
            payload = json.dumps(agent.snapshot).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(('0.0.0.0', port), Handler)
    Thread(target=server.serve_forever, daemon=True).start()
    return server
