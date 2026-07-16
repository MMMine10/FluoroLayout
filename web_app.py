from __future__ import annotations

import io
import base64
import atexit
import json
import mimetypes
import os
import sys
import tempfile
import threading
import traceback
import uuid
import webbrowser
import shutil
import types
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

# The packaged application uses the browser UI only. The historical app.py also
# contains optional Tk classes; provide inert import-time stubs in frozen builds
# so a missing Tcl/Tk runtime cannot block the image-processing core.
if getattr(sys, "frozen", False):
    tk = types.ModuleType("tkinter")
    dummy = type("_TkUnavailable", (), {})
    for name in ("Tk", "Toplevel", "Misc", "Event", "Variable", "StringVar",
                 "BooleanVar", "Canvas"):
        setattr(tk, name, dummy)
    for name in ("filedialog", "messagebox", "simpledialog", "ttk"):
        sub = types.ModuleType(f"tkinter.{name}")
        setattr(tk, name, sub)
        sys.modules[f"tkinter.{name}"] = sub
    sys.modules["tkinter"] = tk

from app import Group, Settings, build_figure, load_group_images


ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
UPLOAD_DIR = Path(tempfile.mkdtemp(prefix="immuno_figure_"))
FILES: dict[str, Path] = {}
atexit.register(lambda: shutil.rmtree(UPLOAD_DIR, ignore_errors=True))


def resolve_group(data: dict) -> Group:
    kwargs = {"name": data.get("name", "实验组"),
              "roi": data.get("roi", [0.55, 0.1, 0.92, 0.47]),
              "included_channels": data.get("included_channels", {
                  "blue": True, "green": True, "red": True, "brightfield": True})}
    for channel in ("blue", "green", "red", "brightfield"):
        token = data.get(channel, "")
        kwargs[channel] = str(FILES[token]) if token in FILES else ""
    return Group(**kwargs)


def make_settings(data: dict) -> Settings:
    allowed = Settings.__dataclass_fields__.keys()
    return Settings(**{k: v for k, v in data.items() if k in allowed})


class Handler(BaseHTTPRequestHandler):
    server_version = "FluoroLayout/1.0"

    def log_message(self, fmt: str, *args) -> None:
        print(f"[FluoroLayout] {fmt % args}")

    def send_bytes(self, data: bytes, content_type: str, status: int = 200,
                   filename: str | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        if filename:
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.end_headers()
        self.wfile.write(data)

    def json_body(self) -> dict:
        n = int(self.headers.get("Content-Length", "0"))
        return json.loads(self.rfile.read(n).decode("utf-8"))

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/":
            path = "/index.html"
        file = ROOT / path.lstrip("/")
        if file.is_file() and file.resolve().parent == ROOT:
            self.send_bytes(file.read_bytes(), mimetypes.guess_type(file.name)[0] or "application/octet-stream")
        else:
            self.send_error(404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/api/shutdown":
                self.send_bytes(b'{"ok":true}', "application/json")
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return
            if parsed.path == "/api/upload":
                n = int(self.headers.get("Content-Length", "0"))
                if n <= 0 or n > 2_000_000_000:
                    raise ValueError("文件为空或超过 2 GB")
                filename = parse_qs(parsed.query).get("filename", ["image.tif"])[0]
                suffix = Path(filename).suffix.lower() or ".tif"
                token = uuid.uuid4().hex
                dest = UPLOAD_DIR / f"{token}{suffix}"
                with dest.open("wb") as f:
                    remaining = n
                    while remaining:
                        chunk = self.rfile.read(min(1024 * 1024, remaining))
                        if not chunk:
                            break
                        f.write(chunk)
                        remaining -= len(chunk)
                FILES[token] = dest
                self.send_bytes(json.dumps({"token": token, "name": filename}).encode(), "application/json")
                return

            data = self.json_body()
            groups = [resolve_group(x) for x in data.get("groups", [])]
            settings = make_settings(data.get("settings", {}))
            if parsed.path == "/api/group-preview":
                if not groups:
                    raise ValueError("没有选中的实验组")
                images = load_group_images(groups[0], settings)
                enabled = [c for c in settings.channel_order
                           if settings.enabled_channels.get(c, False) and c in images
                           and images["_available"].get(c, False)]
                preview_channel = "merge" if "merge" in enabled else (enabled[0] if enabled else "merge")
                image = images[preview_channel]
                buf = io.BytesIO()
                image.save(buf, "PNG")
                self.send_bytes(buf.getvalue(), "image/png")
                return
            if parsed.path in ("/api/figure-preview", "/api/export"):
                image = build_figure(groups, settings)
                buf = io.BytesIO()
                if parsed.path == "/api/figure-preview":
                    image.save(buf, "PNG", dpi=(settings.dpi, settings.dpi))
                    self.send_bytes(buf.getvalue(), "image/png")
                else:
                    fmt = parse_qs(parsed.query).get("format", ["tif"])[0]
                    if fmt == "svg":
                        png = io.BytesIO()
                        image.save(png, "PNG", dpi=(settings.dpi, settings.dpi))
                        encoded = base64.b64encode(png.getvalue()).decode("ascii")
                        svg = (f'<?xml version="1.0" encoding="UTF-8"?>\n'
                               f'<svg xmlns="http://www.w3.org/2000/svg" '
                               f'xmlns:xlink="http://www.w3.org/1999/xlink" '
                               f'width="{image.width}" height="{image.height}" '
                               f'viewBox="0 0 {image.width} {image.height}">\n'
                               f'<image width="{image.width}" height="{image.height}" '
                               f'href="data:image/png;base64,{encoded}"/>\n</svg>')
                        self.send_bytes(svg.encode("utf-8"), "image/svg+xml",
                                        filename="immunofluorescence_figure.svg")
                    elif fmt == "png":
                        image.save(buf, "PNG", dpi=(settings.dpi, settings.dpi))
                        self.send_bytes(buf.getvalue(), "image/png", filename="immunofluorescence_figure.png")
                    else:
                        image.save(buf, "TIFF", compression="tiff_lzw", dpi=(settings.dpi, settings.dpi))
                        self.send_bytes(buf.getvalue(), "image/tiff", filename="immunofluorescence_figure.tif")
                return
            self.send_error(404)
        except Exception as exc:
            payload = json.dumps({"error": str(exc)}, ensure_ascii=False).encode("utf-8")
            self.send_bytes(payload, "application/json; charset=utf-8", status=400)


def main() -> None:
    if "--check" in sys.argv:
        # Used by the launcher smoke test; does not open a browser or keep a server alive.
        assert (ROOT / "index.html").is_file()
        print("FluoroLayout startup check: OK")
        return
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    url = f"http://127.0.0.1:{server.server_port}/"
    port_file = os.environ.get("FLUOROLAYOUT_PORT_FILE")
    if port_file:
        Path(port_file).write_text(str(server.server_port), encoding="ascii")
    print(f"{APP_BANNER}\n本地地址：{url}\n关闭此窗口即可退出。")
    if os.environ.get("FLUOROLAYOUT_NO_BROWSER") != "1":
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        if port_file:
            try:
                Path(port_file).unlink(missing_ok=True)
            except OSError:
                pass


APP_BANNER = "FluoroLayout 已启动（图像仅在本机处理，不会上传网络）"

if __name__ == "__main__":
    try:
        main()
    except Exception:
        log_path = Path(tempfile.gettempdir()) / "FluoroLayout-error.log"
        log_path.write_text(traceback.format_exc(), encoding="utf-8")
        raise
