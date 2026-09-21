"""Temporary Alertmanager webhook receiver: prints each payload and appends it to /captured/alerts.jsonl."""
import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer

CAPTURE_FILE = os.environ.get("CAPTURE_FILE", "/captured/alerts.jsonl")


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        payload = json.loads(body)
        print(f"--- POST {self.path} ---", flush=True)
        print(json.dumps(payload, indent=2, ensure_ascii=False), flush=True)
        with open(CAPTURE_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
        self.send_response(200)
        self.end_headers()


if __name__ == "__main__":
    os.makedirs(os.path.dirname(CAPTURE_FILE), exist_ok=True)
    HTTPServer(("0.0.0.0", 8001), Handler).serve_forever()
