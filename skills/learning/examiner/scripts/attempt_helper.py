#!/usr/bin/env python3
"""Serve one Examiner practice set on 127.0.0.1 and save each attempt the paper sends as attempt-<N>.html there.

Run it in the background while the student sits the paper; it prints one JSON line with the paper's URL, then
serves until stopped. It imports nothing from its own folder, so it writes no bytecode into the installed skill.
"""

from __future__ import annotations

import argparse
import http.server
import json
import mimetypes
import os
import re
import threading
from pathlib import Path
from typing import Any

SET_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-(full-mock|section-practice|topic-practice|supplied-paper)-(\d+)$")
FILE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
ATTEMPT_RE = re.compile(r"^attempt-(\d+)\.html$")
NUMBERED_RE = re.compile(r"^attempt-(\d+)(?:-\d+)?\.html$")
ATTEMPT_DATA_RE = re.compile(r'<script type="application/json" id="paper-attempt-data">(.*?)</script>', re.DOTALL)
TOKEN_RE = re.compile(r"^[a-z0-9]{8,64}$")
MAX_BODY = 5_000_000
WRITE_LOCK = threading.Lock()


def emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload), flush=True)


def set_folder(value: str) -> Path:
    """Return the resolved practice-set folder, or raise ValueError naming what is wrong."""
    try:
        folder = Path(value).resolve(strict=True)
    except (OSError, RuntimeError):
        raise ValueError(f"--set-dir {value!r} does not exist") from None
    if not folder.is_dir():
        raise ValueError(f"{folder} is not a directory")
    if not SET_RE.fullmatch(folder.name):
        raise ValueError(f"{folder.name!r} is not a practice-set folder name such as 2026-10-31-full-mock-01")
    if folder.parent.parent.name != "exams" or folder.parent.parent.parent.parent.name != ".learning":
        raise ValueError(f"{folder} is not under .learning/<subject>/exams/<exam>/")
    if not (folder / "paper.html").is_file():
        raise ValueError(f"{folder} holds no paper.html")
    return folder


def attempt_data(text: str) -> dict[str, Any] | None:
    match = ATTEMPT_DATA_RE.search(text)
    if not match:
        return None
    try:
        data = json.loads(match.group(1))
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def token_of(data: dict[str, Any] | None) -> str | None:
    token = data.get("attemptToken") if data else None
    return token if isinstance(token, str) and TOKEN_RE.fullmatch(token) else None


def save_attempt(folder: Path, token: str, html: str) -> dict[str, Any]:
    """Write html as the attempt holding token: replace its unfinished file, or create the next number."""
    with WRITE_LOCK:
        names = [entry.name for entry in folder.iterdir()]
        matches: list[tuple[int, dict[str, Any]]] = []
        for name in names:
            found = ATTEMPT_RE.fullmatch(name)
            if not found:
                continue
            try:
                data = attempt_data((folder / name).read_text(encoding="utf-8", errors="replace"))
            except OSError:
                continue
            if data is not None and token_of(data) == token:
                matches.append((int(found.group(1)), data))
        data_bytes = html.encode("utf-8")
        if matches:
            number, existing = min(matches, key=lambda item: item[0])
            if existing.get("status") != "finished":
                target = folder / f"attempt-{number}.html"
                temporary = folder / f".attempt-{number}.html.tmp"
                try:
                    temporary.write_bytes(data_bytes)
                    os.replace(temporary, target)
                finally:
                    if temporary.exists():
                        temporary.unlink()
            return {"file": f"attempt-{number}.html", "attempt": number, "created": False}
        number = 1 + max((int(found.group(1)) for name in names if (found := NUMBERED_RE.fullmatch(name))), default=0)
        while True:
            target = folder / f"attempt-{number}.html"
            try:
                with open(target, "xb") as handle:
                    handle.write(data_bytes)
            except FileExistsError:
                number += 1
                continue
            return {"file": f"attempt-{number}.html", "attempt": number, "created": True}


class HelperServer(http.server.ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, folder: Path) -> None:
        super().__init__(("127.0.0.1", 0), Handler)
        self.folder = folder


class Handler(http.server.BaseHTTPRequestHandler):
    server: HelperServer

    def log_message(self, format: str, *args: Any) -> None:
        pass

    def _send(self, status: int, body: bytes, content_type: str, head: bool = False) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if not head:
            self.wfile.write(body)

    def _json(self, status: int, payload: dict[str, Any]) -> None:
        self._send(status, json.dumps(payload).encode("utf-8"), "application/json")

    def _host_ok(self) -> bool:
        port = self.server.server_address[1]
        if self.headers.get("Host") in (f"127.0.0.1:{port}", f"localhost:{port}"):
            return True
        self._json(403, {"error": "this helper answers only on its own address"})
        return False

    def _serve(self, head: bool) -> None:
        if not self._host_ok():
            return
        path = self.path.split("?", 1)[0]
        name = path[1:] if path.startswith("/") else ""
        target = self.server.folder / name
        if not FILE_NAME_RE.fullmatch(name) or not target.is_file():
            self._send(404, b"not found", "text/plain; charset=utf-8", head)
            return
        if target.suffix.lower() == ".html":
            content_type = "text/html; charset=utf-8"
        else:
            content_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
        self._send(200, target.read_bytes(), content_type, head)

    def do_GET(self) -> None:
        self._serve(head=False)

    def do_HEAD(self) -> None:
        self._serve(head=True)

    def do_POST(self) -> None:
        if not self._host_ok():
            return
        if self.path.split("?", 1)[0] != "/attempts":
            self._json(404, {"error": "not found"})
            return
        origin = self.headers.get("Origin")
        if origin is not None and origin != "http://" + str(self.headers.get("Host")):
            self._json(403, {"error": "saves are accepted only from the paper this helper serves"})
            return
        media = (self.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
        if media != "application/json":
            self._json(415, {"error": "the body must be application/json"})
            return
        try:
            length = int(self.headers.get("Content-Length") or "")
        except ValueError:
            length = 0
        if length < 1:
            self._json(411, {"error": "a Content-Length from 1 is required"})
            return
        if length > MAX_BODY:
            self._json(413, {"error": "the attempt is too large"})
            return
        try:
            body = json.loads(self.rfile.read(length).decode("utf-8"))
        except ValueError:
            body = None
        html = body.get("html") if isinstance(body, dict) else None
        token = token_of(attempt_data(html)) if isinstance(html, str) else None
        if not isinstance(html, str) or token is None:
            self._json(400, {"error": "the body holds no answer file with an attempt token"})
            return
        try:
            result = save_attempt(self.server.folder, token, html)
        except OSError as exc:
            self._json(500, {"error": f"the attempt could not be written: {exc}"})
            return
        self._json(200, result)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--set-dir", required=True)
    args = parser.parse_args(argv)
    try:
        folder = set_folder(args.set_dir)
        server = HelperServer(folder)
    except (ValueError, OSError) as exc:
        emit({"status": "blocked", "message": str(exc)})
        return 1
    port = server.server_address[1]
    emit({"status": "serving", "url": f"http://127.0.0.1:{port}/paper.html", "set_dir": str(folder)})
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
