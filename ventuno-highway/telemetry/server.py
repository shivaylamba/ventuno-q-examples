"""Local operator status and optional memory-only native framebuffer preview."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
import time


class Dashboard:
    def __init__(self, port, alive):
        self.status, self.jpeg = {}, None
        self.reset = threading.Event()
        dashboard = self
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/api/status":
                    body=json.dumps(dashboard.status).encode()
                    self.send_response(200); self.send_header("Content-Type","application/json"); self.end_headers(); self.wfile.write(body)
                elif self.path == "/preview.mjpg":
                    self.send_response(200); self.send_header("Content-Type","multipart/x-mixed-replace; boundary=frame"); self.end_headers()
                    try:
                        while alive.is_set():
                            image=dashboard.jpeg
                            if image:
                                self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"+image+b"\r\n")
                            time.sleep(1/6)
                    except (BrokenPipeError,ConnectionResetError): pass
                else:
                    body=b'<!doctype html><title>VENTUNO Q AI Reality Engine</title><style>body{background:#060a17;color:#bcefff;font:18px system-ui;margin:2rem}img{max-width:100%;border-radius:20px}a{color:#bcefff}</style><h1>AI Reality Engine</h1><p>Native GPU game running on VENTUNO Q. Diagnostic preview; HDMI is the primary display.</p><img src="/preview.mjpg"><p><a href="/api/status">Live measurements</a></p>'
                    self.send_response(200); self.send_header("Content-Type","text/html"); self.end_headers(); self.wfile.write(body)
            def do_POST(self):
                if self.path=="/reset": dashboard.reset.set(); self.send_response(204)
                else: self.send_response(404)
                self.end_headers()
            def log_message(self,*_): pass
        self.server=ThreadingHTTPServer(("127.0.0.1",port),Handler)
        self.server.daemon_threads=True
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
    def start(self): self.thread.start()
    def close(self): self.server.shutdown(); self.server.server_close()
