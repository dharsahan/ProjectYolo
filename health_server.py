import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from monitoring import build_health_payload


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in {"/health", "/status", "/metrics"}:
            self.send_response(404)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error":"not found"}')
            return

        payload = build_health_payload()
        body = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        return


def run_health_server(host: str, port: int) -> None:
    server = ThreadingHTTPServer((host, port), HealthHandler)
    server.serve_forever()


def main() -> None:
    parser = argparse.ArgumentParser(description="Yolo health endpoint server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args()
    run_health_server(args.host, args.port)


if __name__ == "__main__":
    main()
