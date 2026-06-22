from __future__ import annotations

import cgi
import html
import os
import subprocess
import sys
import tempfile
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from .analysis import analyze
from .csv_io import read_samples
from .insights import generate_insights
from .report import write_html_report


DEFAULT_MAX_UPLOAD_MB = 25


def _max_upload_bytes() -> int:
    try:
        megabytes = int(os.environ.get("MAX_UPLOAD_MB", str(DEFAULT_MAX_UPLOAD_MB)))
    except ValueError:
        megabytes = DEFAULT_MAX_UPLOAD_MB
    return max(1, min(megabytes, 100)) * 1024 * 1024


MAX_UPLOAD_BYTES = _max_upload_bytes()
MAX_UPLOAD_MB = MAX_UPLOAD_BYTES // (1024 * 1024)
# Multipart form framing is additional to the file itself.
MAX_REQUEST_BYTES = MAX_UPLOAD_BYTES + 1024 * 1024


PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width"><title>Flight Log Analyzer</title><style>
body{font:16px system-ui;background:#0d1726;color:#eaf2ff;max-width:900px;margin:auto;padding:40px 22px}
h1{font-size:38px;margin-bottom:8px}.muted{color:#9fb0c8}.panel{background:#15243a;border:1px solid #2c4262;border-radius:16px;padding:26px;margin-top:28px}
.drop{display:block;border:2px dashed #58769e;border-radius:13px;padding:48px 20px;text-align:center;cursor:pointer;background:#101d30}.drop:hover{border-color:#56b4e9}
input[type=file]{margin:18px 0}button{background:#56b4e9;color:#07111f;border:0;border-radius:9px;padding:12px 22px;font-weight:700;font-size:16px;cursor:pointer}
.note{font-size:14px;margin-top:18px}.error{background:#4c1f29;border:1px solid #b95162;padding:14px;border-radius:9px;margin-top:18px}
</style></head><body><h1>Flight Log Analyzer</h1><p class="muted">Upload Mission Planner telemetry or an ArduPilot onboard log.</p>
<main class="panel"><form method="post" enctype="multipart/form-data" action="/analyze">
<label class="drop"><strong>Choose a .tlog or .BIN file</strong><br><span class="muted">Mission Planner telemetry or flight-controller DataFlash log</span><br>
<input required type="file" name="flight_log" accept=".tlog,.bin"></label><p><button type="submit">Analyze flight</button></p></form>
<p class="muted note">Uploads are deleted after processing. Maximum file size: {max_upload_mb} MB. The assessment is an engineering aid, not a certified safety determination.</p>{error}</main></body></html>"""


def _page(error: str = "") -> bytes:
    return PAGE.replace("{max_upload_mb}", str(MAX_UPLOAD_MB)).replace("{error}", error).encode()


def _read_flight_log(upload: Path, suffix: str, temp_dir: str):
    normalized = Path(temp_dir) / "normalized.csv"
    command = "import-tlog" if suffix == ".tlog" else "import-bin"
    try:
        result = subprocess.run(
            [sys.executable, "-m", "flightrecorder", command, str(upload), str(normalized)],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise ValueError("Flight-log parsing exceeded the 120-second limit") from error
    if result.returncode != 0:
        raise ValueError("The flight log could not be parsed")
    return read_samples(normalized)


class DashboardHandler(BaseHTTPRequestHandler):
    def _send(self, body: bytes, content_type: str = "text/html; charset=utf-8", status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = unquote(urlparse(self.path).path)
        if path == "/":
            self._send(_page())
            return
        self._send(b"Not found", "text/plain", 404)

    def do_POST(self):
        if self.path != "/analyze":
            self._send(b"Not found", "text/plain", 404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > MAX_REQUEST_BYTES:
                raise ValueError(f"The upload is empty or exceeds {MAX_UPLOAD_MB} MB")
            form = cgi.FieldStorage(
                fp=self.rfile,
                headers=self.headers,
                environ={"REQUEST_METHOD": "POST", "CONTENT_TYPE": self.headers.get("Content-Type", "")},
            )
            if "flight_log" not in form:
                raise ValueError("No flight log was uploaded")
            item = form["flight_log"]
            if isinstance(item, list) or not getattr(item, "file", None):
                raise ValueError("Please upload one flight log")
            original = Path(item.filename or "").name
            suffix = Path(original).suffix.lower()
            if suffix not in {".tlog", ".bin"}:
                raise ValueError("Please select a .tlog or .BIN file")
            with tempfile.TemporaryDirectory(prefix="flight-analyzer-") as temp_dir:
                token = uuid.uuid4().hex[:10]
                upload = Path(temp_dir) / f"{token}{suffix}"
                uploaded_bytes = 0
                with upload.open("wb") as destination:
                    while block := item.file.read(1024 * 1024):
                        uploaded_bytes += len(block)
                        if uploaded_bytes > MAX_UPLOAD_BYTES:
                            raise ValueError(f"The upload exceeds {MAX_UPLOAD_MB} MB")
                        destination.write(block)
                if uploaded_bytes == 0:
                    raise ValueError("The uploaded file is empty")

                samples = _read_flight_log(upload, suffix, temp_dir)
                report = Path(temp_dir) / f"flight_report_{token}.html"
                write_html_report(report, samples, analyze(samples), generate_insights(samples))
                report_bytes = report.read_bytes()

            self._send(report_bytes)
        except Exception as error:
            message = f'<div class="error"><strong>Analysis failed:</strong> {html.escape(str(error))}</div>'
            self._send(_page(message), status=400)

    def log_message(self, format, *args):
        print(f"Dashboard: {format % args}")


def run_dashboard(host: str = "127.0.0.1", port: int = 8765, open_browser: bool = True) -> None:
    server = ThreadingHTTPServer((host, port), DashboardHandler)
    url = f"http://{host}:{port}"
    print(f"Flight Log Analyzer running at {url}")
    print("Press Ctrl+C to stop it.")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
