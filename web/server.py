#!/usr/bin/env python3
"""
AGOS — Web Dashboard Server
Serves the premium web UI and proxies agent commands.
This runs as the local daemon — handles HTTP + agent execution.
"""

import asyncio
import json
import logging
import os
import sys
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
import threading

import urllib.request
import urllib.error

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
                    datefmt="%H:%M:%S")
logger = logging.getLogger("agos.web")

WEB_DIR = Path(__file__).parent
PORT = int(os.getenv("AGOS_PORT", "8765"))
KERNEL_URL = os.getenv("KERNEL_URL", "http://localhost:9000")

task_history = []


class AGOSHandler(SimpleHTTPRequestHandler):
    """HTTP handler for AGOS web dashboard."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB_DIR), **kwargs)

    def _proxy_kernel(self, path, method="GET", body=None):
        """Proxy request to the Go Kernel."""
        url = f"{KERNEL_URL}{path}"
        try:
            req = urllib.request.Request(url, data=body, method=method)
            req.add_header("Content-Type", "application/json")
            
            with urllib.request.urlopen(req, timeout=30) as response:
                data = response.read()
                self.send_response(response.status)
                for key, val in response.getheaders():
                    if key.lower() not in ("content-length", "transfer-encoding"):
                        self.send_header(key, val)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(data)
                return True
        except urllib.error.HTTPError as e:
            self._json_response({"error": e.reason}, e.code)
            return True
        except Exception as e:
            logger.error(f"[PROXY] Connection failed to {url}: {e}")
            return False

    def do_GET(self):
        """Handle GET requests."""
        if self.path.startswith("/api/v1/"):
            if not self._proxy_kernel(self.path):
                self._json_response({"error": "Kernel offline"}, 503)
            return

        if self.path == "/health":
            self._json_response({
                "status": "healthy",
                "mode": "Gateway (V4.1)",
                "kernel_url": KERNEL_URL
            })
        elif self.path == "/metrics":
            if not self._proxy_kernel(self.path):
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(b"agos_up 0\n")
        elif self.path.startswith("/static/") or self.path == "/":
            if self.path == "/":
                self.path = "/index.html"
            super().do_GET()
        else:
            super().do_GET()

    def do_POST(self):
        """Handle POST requests."""
        if self.path.startswith("/api/v1/"):
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            if not self._proxy_kernel(self.path, method="POST", body=body):
                self._json_response({"error": "Kernel offline"}, 503)
            return

        if self.path == "/api/v1/auth/login":
            # Simple auth maintained for UI session initialization
            self._json_response({
                "access_token": "agos_dev_token",
                "user": {"email": "admin@agos.dev", "role": "admin"},
            })
        else:
            self._json_response({"error": "not found"}, 404)

    def do_OPTIONS(self):
        """Handle CORS preflight."""
        self.send_response(200)
        self._cors_headers()
        self.end_headers()

    def _json_response(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self._cors_headers()
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def _cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

    def log_message(self, format, *args):
        # Suppress default logging for static files
        if "/static/" not in str(args[0]):
            logger.info(f"[HTTP] {args[0]}")


def main():
    server = HTTPServer(("0.0.0.0", PORT), AGOSHandler)
    logger.info("╔══════════════════════════════════════════╗")
    logger.info("║     AGOS Web Dashboard                    ║")
    logger.info("╚══════════════════════════════════════════╝")
    logger.info(f"🌐 Dashboard: http://localhost:{PORT}")
    logger.info(f"📡 API:       http://localhost:{PORT}/api/v1/")
    logger.info(f"❤️  Health:    http://localhost:{PORT}/health")
    logger.info(f"📊 Metrics:   http://localhost:{PORT}/metrics")
    logger.info("")
    logger.info("Groq API: " + ("✅ configured" if os.getenv("GROQ_API_KEY") else "❌ set GROQ_API_KEY"))
    logger.info("Ready. Open your browser to http://localhost:8765")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        server.shutdown()


if __name__ == "__main__":
    main()
