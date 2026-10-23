#!/usr/bin/env python3
"""Drive a headless Chrome or Edge through Examiner's paper runtime on a throwaway paper and check its behaviour."""

from __future__ import annotations


# Public command execution starts in a contained worker before project imports.
import sys as _sys
import time as _time

_VALIDATION_START = _time.monotonic()
from pathlib import Path as _Path
from validation_budget import bounded_main as _bounded_main

if __name__ == "__main__":
    raise SystemExit(_bounded_main(_Path(__file__), _sys.argv[1:], _Path(__file__).resolve().parents[2], started_at=_VALIDATION_START))

import argparse
import base64
import json
import os
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tools" / "validation" / "paper_runtime_fixture.html"
RUNTIME = ROOT / "skills" / "learning" / "examiner" / "assets" / "paper-runtime.html"
MARKER = "<!-- paper-runtime -->"
STORED = "JSON.parse(localStorage.getItem('ffh-paper:runtime-exercise-01'))"
ANSWER_FILE = "answers-runtime-exercise-01.html"
BLOCK_STORAGE = "Object.defineProperty(window,'localStorage',{get(){throw new DOMException('blocked','SecurityError')}})"
BROWSER_NAMES = ("chrome", "google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "msedge", "microsoft-edge")
BROWSER_PATHS = (
    ("PROGRAMFILES", r"Google\Chrome\Application\chrome.exe"),
    ("PROGRAMFILES(X86)", r"Google\Chrome\Application\chrome.exe"),
    ("LOCALAPPDATA", r"Google\Chrome\Application\chrome.exe"),
    ("PROGRAMFILES(X86)", r"Microsoft\Edge\Application\msedge.exe"),
    ("PROGRAMFILES", r"Microsoft\Edge\Application\msedge.exe"),
)
MAC_PATHS = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
)
EXPECTED_CHECKS = 22


class ExerciseError(Exception):
    """A browser, protocol, or check failure."""


def find_browser(explicit: str | None) -> str:
    if explicit:
        return explicit
    for name in BROWSER_NAMES:
        found = shutil.which(name)
        if found and Path(found).exists():
            return found
    candidates: list[Path] = []
    for variable, relative in BROWSER_PATHS:
        base = os.environ.get(variable)
        if base:
            candidates.append(Path(base) / relative)
    candidates.extend(Path(path) for path in MAC_PATHS)
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    raise ExerciseError("no Chrome or Edge found; pass --browser <path>")


class Session:
    """One headless browser on one profile, spoken to over the DevTools protocol."""

    def __init__(self, browser: str, profile: Path, downloads: Path) -> None:
        self.profile = profile
        self.downloads = downloads
        self.events: list[dict[str, Any]] = []
        self.sock: socket.socket | None = None
        self.buffer = b""
        self.next_id = 0
        self.closed = False
        port_file = profile / "DevToolsActivePort"
        if port_file.exists():
            port_file.unlink()
        self.process = subprocess.Popen(
            [browser, "--headless=new", "--remote-debugging-port=0", f"--user-data-dir={profile}",
             "--no-first-run", "--no-default-browser-check", "--disable-extensions", "about:blank"],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )

    def connect(self) -> None:
        port_file = self.profile / "DevToolsActivePort"
        deadline = time.monotonic() + 20
        port = ""
        while time.monotonic() < deadline:
            if port_file.exists():
                lines = port_file.read_text(encoding="utf-8", errors="replace").splitlines()
                if lines and lines[0].strip().isdigit():
                    port = lines[0].strip()
                    break
            time.sleep(0.1)
        if not port:
            raise ExerciseError("no DevTools port within 20 s")
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        target = ""
        while not target:
            try:
                with opener.open(f"http://127.0.0.1:{port}/json/list", timeout=5) as response:
                    listing = json.loads(response.read().decode("utf-8"))
                target = next((entry["webSocketDebuggerUrl"] for entry in listing if entry.get("type") == "page"), "")
            except OSError:
                target = ""
            if not target:
                if time.monotonic() >= deadline:
                    raise ExerciseError("no DevTools page target within 20 s")
                time.sleep(0.1)
        self._handshake(target)
        self.call("Page.enable")
        self.call("Network.enable")
        self.call("Browser.setDownloadBehavior",
                  {"behavior": "allow", "downloadPath": str(self.downloads), "eventsEnabled": True})

    def _handshake(self, url: str) -> None:
        parsed = urllib.parse.urlsplit(url)
        host = parsed.hostname or "127.0.0.1"
        sock = socket.create_connection((host, parsed.port or 80), timeout=10)
        self.sock = sock
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        request = (f"GET {parsed.path} HTTP/1.1\r\nHost: {host}:{parsed.port}\r\nUpgrade: websocket\r\n"
                   f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n")
        sock.sendall(request.encode("ascii"))
        response = b""
        while b"\r\n\r\n" not in response:
            chunk = sock.recv(4096)
            if not chunk:
                raise ExerciseError("DevTools WebSocket handshake closed")
            response += chunk
        head, _, rest = response.partition(b"\r\n\r\n")
        if b" 101 " not in head.split(b"\r\n", 1)[0] + b" ":
            raise ExerciseError(f"DevTools WebSocket handshake refused: {head.decode('latin-1')}")
        self.buffer = rest

    def _send_frame(self, opcode: int, payload: bytes) -> None:
        if self.sock is None:
            raise ExerciseError("DevTools socket is not connected")
        header = bytes([0x80 | opcode])
        length = len(payload)
        if length < 126:
            header += bytes([0x80 | length])
        elif length < 65536:
            header += bytes([0x80 | 126]) + struct.pack("!H", length)
        else:
            header += bytes([0x80 | 127]) + struct.pack("!Q", length)
        mask = os.urandom(4)
        masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        self.sock.sendall(header + mask + masked)

    def _parse_frame(self) -> tuple[bool, int, bytes] | None:
        data = self.buffer
        if len(data) < 2:
            return None
        fin = bool(data[0] & 0x80)
        opcode = data[0] & 0x0F
        masked = bool(data[1] & 0x80)
        length = data[1] & 0x7F
        offset = 2
        if length == 126:
            if len(data) < 4:
                return None
            length = struct.unpack("!H", data[2:4])[0]
            offset = 4
        elif length == 127:
            if len(data) < 10:
                return None
            length = struct.unpack("!Q", data[2:10])[0]
            offset = 10
        mask = b""
        if masked:
            if len(data) < offset + 4:
                return None
            mask = data[offset:offset + 4]
            offset += 4
        if len(data) < offset + length:
            return None
        payload = data[offset:offset + length]
        if masked:
            payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        self.buffer = data[offset + length:]
        return fin, opcode, payload

    def _read_message(self, deadline: float) -> str | None:
        """Return one whole text message, or None when the deadline passes first."""
        if self.sock is None:
            raise ExerciseError("DevTools socket is not connected")
        parts: list[bytes] = []
        while True:
            frame = self._parse_frame()
            if frame is None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    if parts:
                        raise ExerciseError("DevTools message did not complete in time")
                    return None
                self.sock.settimeout(remaining)
                try:
                    chunk = self.sock.recv(65536)
                except socket.timeout:
                    continue
                if not chunk:
                    raise ExerciseError("DevTools connection closed")
                self.buffer += chunk
                continue
            fin, opcode, payload = frame
            if opcode == 0x9:
                self._send_frame(0xA, payload)
                continue
            if opcode == 0xA:
                continue
            if opcode == 0x8:
                raise ExerciseError("DevTools connection sent close")
            parts.append(payload)
            if fin:
                return b"".join(parts).decode("utf-8")

    def _receive(self, deadline: float) -> dict[str, Any] | None:
        text = self._read_message(deadline)
        if text is None:
            return None
        message: dict[str, Any] = json.loads(text)
        if "method" in message:
            self.events.append(message)
        return message

    def call(self, method: str, params: dict[str, Any] | None = None, timeout: float = 30) -> dict[str, Any]:
        self.next_id += 1
        ident = self.next_id
        self._send_frame(0x1, json.dumps({"id": ident, "method": method, "params": params or {}}).encode("utf-8"))
        deadline = time.monotonic() + timeout
        while True:
            message = self._receive(deadline)
            if message is None:
                raise ExerciseError(f"{method} got no reply within {timeout:g} s")
            if message.get("id") == ident:
                if "error" in message:
                    raise ExerciseError(f"{method} failed: {message['error']}")
                result: dict[str, Any] = message.get("result", {})
                return result

    def pump(self, seconds: float) -> None:
        deadline = time.monotonic() + seconds
        while self._receive(deadline) is not None:
            pass

    def events_named(self, method: str) -> list[dict[str, Any]]:
        return [event for event in self.events if event.get("method") == method]

    def clear_events(self, method: str) -> None:
        self.events = [event for event in self.events if event.get("method") != method]

    def _wait_load(self, what: str) -> None:
        deadline = time.monotonic() + 10
        while not self.events_named("Page.loadEventFired"):
            if self._receive(deadline) is None:
                raise ExerciseError(f"{what} did not finish loading within 10 s")

    def navigate(self, url: str) -> None:
        self.clear_events("Page.loadEventFired")
        result = self.call("Page.navigate", {"url": url})
        if result.get("errorText"):
            raise ExerciseError(f"navigation to {url} failed: {result['errorText']}")
        self._wait_load(url)

    def reload(self) -> None:
        self.clear_events("Page.loadEventFired")
        self.call("Page.reload")
        self._wait_load("reload")

    def evaluate(self, expression: str) -> Any:
        result = self.call("Runtime.evaluate", {"expression": expression, "returnByValue": True, "awaitPromise": True})
        if "exceptionDetails" in result:
            details = result["exceptionDetails"]
            description = details.get("exception", {}).get("description") or details.get("text")
            raise ExerciseError(f"page script failed: {description}")
        return result.get("result", {}).get("value")

    def wait_until(self, expression: str, seconds: float) -> None:
        deadline = time.monotonic() + seconds
        while self.evaluate(expression) is not True:
            if time.monotonic() >= deadline:
                raise ExerciseError(f"timed out after {seconds:g} s waiting for {expression}")
            time.sleep(0.1)

    def sleep_until(self, epoch_ms: float) -> None:
        while float(self.evaluate("Date.now()")) < epoch_ms:
            time.sleep(0.1)

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        if self.sock is not None and self.process.poll() is None:
            try:
                self.next_id += 1
                self._send_frame(0x1, json.dumps({"id": self.next_id, "method": "Browser.close", "params": {}}).encode("utf-8"))
            except OSError:
                pass
        try:
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        if self.sock is not None:
            try:
                self.sock.close()
            except OSError:
                pass


class Page:
    """Reads and actions on the paper through the runtime's ids and attributes."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def js(self, expression: str) -> Any:
        return self.session.evaluate(expression)

    def status(self) -> Any:
        return self.js("document.documentElement.getAttribute('data-paper-status')")

    def part(self) -> Any:
        return self.js("document.documentElement.getAttribute('data-paper-part')")

    def exists(self, selector: str) -> bool:
        return self.js(f"document.querySelector({json.dumps(selector)}) !== null") is True

    def visible(self, selector: str) -> bool:
        return self.js(f"(() => {{ const e = document.querySelector({json.dumps(selector)}); "
                       "return !!e && e.getClientRects().length > 0; })()") is True

    def attr(self, selector: str, name: str) -> Any:
        return self.js(f"(() => {{ const e = document.querySelector({json.dumps(selector)}); "
                       f"return e ? e.getAttribute({json.dumps(name)}) : null; }})()")

    def number(self, selector: str, name: str) -> int:
        value = self.attr(selector, name)
        if value is None:
            raise ExerciseError(f"{selector} has no {name}")
        return int(value)

    def text(self, selector: str) -> str:
        return str(self.js(f"(() => {{ const e = document.querySelector({json.dumps(selector)}); "
                           "return e ? e.textContent : ''; })()"))

    def disabled(self, selector: str) -> bool:
        return self.js(f"(() => {{ const e = document.querySelector({json.dumps(selector)}); "
                       "return !!e && e.disabled; })()") is True

    def click(self, selector: str) -> None:
        clicked = self.js(f"(() => {{ const e = document.querySelector({json.dumps(selector)}); "
                          "if (!e) return false; e.click(); return true; })()")
        if clicked is not True:
            raise ExerciseError(f"nothing to click at {selector}")

    def set_text(self, selector: str, value: str) -> None:
        done = self.js(f"(() => {{ const e = document.querySelector({json.dumps(selector)}); if (!e) return false; "
                       f"e.value = {json.dumps(value)}; e.dispatchEvent(new Event('input', {{bubbles: true}})); return true; }})()")
        if done is not True:
            raise ExerciseError(f"no text control at {selector}")

    def value(self, selector: str) -> Any:
        return self.js(f"(() => {{ const e = document.querySelector({json.dumps(selector)}); return e ? e.value : null; }})()")

    def checked(self, selector: str) -> bool:
        return self.js(f"(() => {{ const e = document.querySelector({json.dumps(selector)}); "
                       "return !!e && e.checked; })()") is True

    def visible_questions(self) -> list[str]:
        value = self.js("Array.from(document.querySelectorAll('.paper-question'))"
                        ".filter(e => e.getClientRects().length > 0).map(e => e.getAttribute('data-question'))")
        return [str(item) for item in value]

    def palette(self) -> list[dict[str, Any]]:
        value = self.js("Array.from(document.querySelectorAll('#paper-palette button')).map(b => ({"
                        "question: b.getAttribute('data-palette-question'), state: b.getAttribute('data-state'), "
                        "flagged: b.getAttribute('data-flagged'), disabled: b.disabled}))")
        return list(value)

    def palette_entry(self, number: str) -> dict[str, Any]:
        for entry in self.palette():
            if entry["question"] == number:
                return entry
        raise ExerciseError(f"palette has no question {number}")

    def remaining(self, selector: str = "#paper-clock") -> int:
        return self.number(selector, "data-remaining-ms")

    def stored(self) -> Any:
        return self.js(STORED)

    def locked(self) -> bool:
        return self.js(
            "(() => { const controls = Array.from(document.querySelectorAll("
            "'.paper-question input, .paper-question textarea, .paper-question select'));"
            " const ids = ['#paper-load', '#paper-flag', '#paper-previous', '#paper-next', '#paper-submit'];"
            " return controls.every(e => e.disabled) && ids.every(s => { const e = document.querySelector(s);"
            " return !!e && e.disabled; }); })()") is True

    def now(self) -> float:
        return float(self.js("Date.now()"))


class Checks:
    def __init__(self) -> None:
        self.passed = 0

    def run(self, ident: str, assertions: list[tuple[bool, str]]) -> None:
        for holds, what in assertions:
            if not holds:
                raise ExerciseError(f"{ident}: {what}")
        self.passed += 1


def _normal(url: str) -> str:
    return urllib.parse.unquote(url).lower()


def _foreign_requests(events: list[dict[str, Any]], allowed: list[str]) -> list[str]:
    allowed_forms = {_normal(url) for url in allowed}
    foreign: list[str] = []
    for event in events:
        if event.get("method") != "Network.requestWillBeSent":
            continue
        url = str(event.get("params", {}).get("request", {}).get("url", ""))
        if url.startswith(("data:", "blob:", "about:")):
            continue
        if url.startswith("file:") and _normal(url) in allowed_forms:
            continue
        foreign.append(url)
    return foreign


def _replace_once(text: str, old: str, new: str, what: str) -> str:
    if text.count(old) != 1:
        raise ExerciseError(f"{what}: expected {old!r} exactly once")
    return text.replace(old, new)


def write_papers(temp: Path) -> dict[str, Path]:
    fixture = FIXTURE.read_text(encoding="utf-8")
    runtime = RUNTIME.read_text(encoding="utf-8")
    if fixture.splitlines().count(MARKER) != 1:
        raise ExerciseError(f"the fixture must hold the line {MARKER} exactly once")
    paper_a = _replace_once(fixture, MARKER, runtime.rstrip("\n"), "fixture")
    paper_b = _replace_once(paper_a, '"access": {"extraTimePercent": 50, "restBreaks": true}', '"access": {}', "paper b")
    paper_c = _replace_once(paper_a, '"minutes": 0.5', '"minutes": 0', "paper c")
    papers: dict[str, Path] = {}
    for name, text in (("a", paper_a), ("b", paper_b), ("c", paper_c)):
        path = temp / name / "paper.html"
        path.parent.mkdir(parents=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        papers[name] = path
    return papers


def scenario_a(open_session: Any, papers: dict[str, Path], temp: Path, checks: Checks) -> str:
    url = papers["a"].as_uri()
    session: Session = open_session("profile-a")
    product = str(session.call("Browser.getVersion").get("product", "an unknown browser"))
    page = Page(session)
    requests: list[dict[str, Any]] = []
    session.navigate(url)
    checks.run("A1", [
        (page.status() == "not-started", f"status is {page.status()!r}, not not-started"),
        (page.visible("#paper-practice-notice"), "#paper-practice-notice is not visible"),
        ("50%" in page.text("#paper-start-screen"), "#paper-start-screen does not mention 50%"),
        (page.exists("#paper-rest"), "#paper-rest is missing"),
        (page.visible_questions() == [], f"questions visible before start: {page.visible_questions()}"),
        (not page.visible("#paper-new-attempt"), "#paper-new-attempt is visible"),
    ])

    page.click("#paper-start")
    left = page.remaining()
    checks.run("A2", [
        (page.status() == "running", f"status is {page.status()!r}, not running"),
        (page.part() == "p1", f"part is {page.part()!r}, not p1"),
        (40000 < left <= 45000, f"remaining {left} ms is not in (40000, 45000]"),
    ])

    palette = page.palette()
    checks.run("A3", [
        ([entry["question"] for entry in palette] == ["1", "2", "3"], f"palette is {palette}"),
        ([entry["state"] for entry in palette] == ["unanswered", "not-visited", "not-visited"], f"palette states are {palette}"),
        (page.visible_questions() == ["1"], f"visible questions are {page.visible_questions()}"),
    ])

    page.click("input[name='q1'][value='A']")
    checks.run("A4", [
        (page.palette_entry("1")["state"] == "answered", "palette 1 is not answered"),
        (page.attr("#paper-summary", "data-answered") == "1", "summary data-answered is not 1"),
    ])

    page.click("#paper-next")
    page.click("#paper-flag")
    entry = page.palette_entry("2")
    checks.run("A5", [
        (entry["state"] == "unanswered" and entry["flagged"] == "true", f"palette 2 is {entry}"),
        (page.attr("#paper-summary", "data-unanswered") == "2", "summary data-unanswered is not 2"),
        (page.attr("#paper-summary", "data-flagged") == "1", "summary data-flagged is not 1"),
    ])

    page.click("#paper-palette button[data-palette-question='3']")
    page.set_text("#q3", "Rain fell all day.")
    checks.run("A6", [(page.palette_entry("3")["state"] == "answered", "palette 3 is not answered")])
    before = page.remaining()

    def restored(ident: str, low: int, high: int, label: str) -> None:
        entry = page.palette_entry("2")
        left = page.remaining()
        checks.run(ident, [
            (page.status() == "running", f"status is {page.status()!r}, not running"),
            (page.checked("input[name='q1'][value='A']"), "radio q1 A is not checked"),
            (page.value("#q3") == "Rain fell all day.", f"q3 is {page.value('#q3')!r}"),
            (entry["state"] == "unanswered" and entry["flagged"] == "true", f"palette 2 is {entry}"),
            (page.visible_questions() == ["3"], f"visible questions are {page.visible_questions()}"),
            (low < left <= high, f"remaining {left} ms is not in ({low}, {high}] ({label})"),
        ])

    session.reload()
    restored("A7", before - 10000, before - 1, "after reload")

    page.click("#paper-rest")
    status = page.status()
    hidden = page.visible_questions() == []
    frozen = page.remaining()
    page.session.sleep_until(page.now() + 2000)
    later = page.remaining()
    page.click("#paper-rest")
    resumed = page.remaining()
    checks.run("A8", [
        (status == "rest", f"status is {status!r}, not rest"),
        (hidden, "a question is visible during the rest break"),
        (abs(later - frozen) <= 300, f"remaining moved from {frozen} to {later} ms during the rest break"),
        (page.status() == "running", f"status is {page.status()!r} after the rest break"),
        (resumed > frozen - 1500, f"remaining {resumed} ms fell too far below {frozen} ms"),
    ])

    left = page.remaining()
    started = page.now()
    requests.extend(session.events)
    session.close()
    session = open_session("profile-a")
    page = Page(session)
    session.sleep_until(started + 3000)
    session.navigate(url)
    restored("A9", left - 12000, left - 3000, "after reopening")

    page.click("#paper-submit")
    confirm_visible = page.visible("#paper-submit-confirm")
    confirm_count = page.attr("#paper-submit-confirm", "data-unanswered")
    page.click("#paper-submit-yes")
    break_left = page.remaining("#paper-break-clock")
    stored = page.stored()
    break_ends = stored.get("breakEndsAt") if isinstance(stored, dict) else None
    checks.run("A10", [
        (confirm_visible, "#paper-submit-confirm is not visible"),
        (confirm_count == "1", f"#paper-submit-confirm data-unanswered is {confirm_count!r}"),
        (page.status() == "break", f"status is {page.status()!r}, not break"),
        (0 < break_left <= 3000, f"break remaining {break_left} ms is not in (0, 3000]"),
        (page.visible_questions() == [], "a question is visible during the break"),
        (isinstance(break_ends, (int, float)) and not isinstance(break_ends, bool), f"stored breakEndsAt is {break_ends!r}"),
    ])
    assert isinstance(break_ends, (int, float))

    session.navigate("about:blank")
    session.sleep_until(break_ends + 1000)
    session.navigate(url)
    stored = page.stored()
    left = page.remaining()
    palette = page.palette()
    checks.run("A11", [
        (page.status() == "running", f"status is {page.status()!r}, not running"),
        (page.part() == "p2", f"part is {page.part()!r}, not p2"),
        (stored["parts"][1]["startedAt"] == break_ends, f"part 2 started at {stored['parts'][1]['startedAt']}, not {break_ends}"),
        (0 < left <= 8000, f"remaining {left} ms is not in (0, 8000]"),
        (page.disabled("#paper-previous"), "#paper-previous is enabled in a forward-only part"),
        (bool(palette) and all(entry["disabled"] for entry in palette), f"palette buttons are not all disabled: {palette}"),
    ])

    page.set_text("#q4", "7")
    page.click("#paper-next")
    checks.run("A12", [
        (page.visible_questions() == ["5"], f"visible questions are {page.visible_questions()}"),
        (page.disabled("#paper-previous"), "#paper-previous is enabled in a forward-only part"),
    ])

    stored = page.stored()
    deadline = stored["parts"][1]["startedAt"] + 9000 + stored["parts"][1]["restMs"]
    session.navigate("about:blank")
    session.sleep_until(deadline + 1000)
    session.clear_events("Browser.downloadWillBegin")
    session.navigate(url)
    stored = page.stored()
    href = page.attr("#paper-attempt-download", "href")
    download = page.attr("#paper-attempt-download", "download")
    wait_end = time.monotonic() + 5
    while not session.events_named("Browser.downloadWillBegin") and time.monotonic() < wait_end:
        session.pump(0.2)
    session.pump(0.5)
    downloads = session.events_named("Browser.downloadWillBegin")
    checks.run("A13", [
        (page.status() == "finished", f"status is {page.status()!r}, not finished"),
        (stored["parts"][1]["endedBy"] == "expired", f"part 2 ended by {stored['parts'][1]['endedBy']!r}"),
        (stored["parts"][1]["endedAt"] == deadline, f"part 2 ended at {stored['parts'][1]['endedAt']}, not {deadline}"),
        (stored["parts"][0]["endedBy"] == "submitted", f"part 1 ended by {stored['parts'][0]['endedBy']!r}"),
        (page.locked(), "the finished paper is not locked"),
        (page.visible("#paper-attempt"), "#paper-attempt is not visible"),
        (download == ANSWER_FILE, f"download name is {download!r}"),
        (isinstance(href, str) and href.startswith("blob:"), f"href is {href!r}"),
        (len(downloads) == 1, f"{len(downloads)} downloads began, not 1"),
        (bool(downloads) and downloads[0]["params"].get("suggestedFilename") == ANSWER_FILE,
         f"download suggested {downloads[0]['params'].get('suggestedFilename') if downloads else None!r}"),
    ])

    answer_text = str(page.js(f"fetch({json.dumps(href)}).then(response => response.text())"))
    data = page.js(f"JSON.parse(new DOMParser().parseFromString({json.dumps(answer_text)}, 'text/html')"
                   ".getElementById('paper-attempt-data').textContent)")
    answers = data.get("answers", {}) if isinstance(data, dict) else {}
    checks.run("A14", [
        ("This file was made on your device" in answer_text, "the answer file lacks the on-device sentence"),
        ("Attempt 1" in answer_text, "the answer file lacks Attempt 1"),
        ("Question 2: no answer (flagged for review)" in answer_text, "the answer file lacks the flagged unanswered question 2"),
        (isinstance(data, dict) and data.get("id") == "runtime-exercise-01", "attempt data id differs"),
        (answers.get("q1") == "A", f"attempt data q1 is {answers.get('q1')!r}"),
        (answers.get("q3") == "Rain fell all day.", f"attempt data q3 is {answers.get('q3')!r}"),
        (answers.get("q4") == "7", f"attempt data q4 is {answers.get('q4')!r}"),
        (isinstance(data, dict) and "2" in data.get("flags", []), "attempt data flags lack 2"),
        (isinstance(data, dict) and data["parts"][0]["endedBy"] == "submitted", "attempt data part 1 not submitted"),
        (isinstance(data, dict) and data["parts"][1]["endedBy"] == "expired", "attempt data part 2 not expired"),
    ])
    (temp / "answers.html").write_text(answer_text, encoding="utf-8", newline="\n")

    session.clear_events("Browser.downloadWillBegin")
    session.reload()
    session.sleep_until(page.now() + 2000)
    checks.run("A15", [
        (page.status() == "finished", f"status is {page.status()!r}, not finished"),
        (page.locked(), "the finished paper is not locked after reload"),
        (page.exists("#paper-attempt-download"), "#paper-attempt-download is missing"),
        (not session.events_named("Browser.downloadWillBegin"), "a download began again after reload"),
    ])

    page.click("#paper-new-attempt")
    confirm_visible = page.visible("#paper-new-attempt-confirm")
    page.click("#paper-new-attempt-yes")
    stored = page.stored()
    checks.run("A16", [
        (confirm_visible, "#paper-new-attempt-confirm is not visible"),
        (page.status() == "not-started", f"status is {page.status()!r}, not not-started"),
        (stored["attempt"] == 2, f"stored attempt is {stored['attempt']!r}"),
        (page.js("Array.from(document.querySelectorAll(\"input[name='q1']\")).some(e => e.checked)") is False,
         "a q1 radio is still checked"),
        (page.value("#q3") == "", f"q3 is {page.value('#q3')!r}"),
    ])

    requests.extend(session.events)
    foreign = _foreign_requests(requests, [url])
    checks.run("A17", [(not foreign, f"requests outside the paper: {foreign}")])
    session.close()
    return product


def scenario_b(open_session: Any, papers: dict[str, Path], temp: Path, checks: Checks) -> None:
    url_b = papers["b"].as_uri()
    url_c = papers["c"].as_uri()
    session: Session = open_session("profile-b")
    page = Page(session)
    session.call("Page.addScriptToEvaluateOnNewDocument", {"source": BLOCK_STORAGE})
    session.navigate(url_b)
    checks.run("B1", [
        (page.status() == "not-started", f"status is {page.status()!r}, not not-started"),
        (page.visible("#paper-storage-warning"), "#paper-storage-warning is not visible"),
        (not page.exists("#paper-rest"), "#paper-rest exists without a rest-break arrangement"),
        ("extra time" not in page.text("#paper-start-screen"), "#paper-start-screen mentions extra time"),
    ])

    page.click("#paper-start")
    left = page.remaining()
    checks.run("B2", [
        (page.status() == "running", f"status is {page.status()!r}, not running"),
        (25000 < left <= 30000, f"remaining {left} ms is not in (25000, 30000]"),
    ])

    document = session.call("DOM.getDocument")
    node = session.call("DOM.querySelector", {"nodeId": document["root"]["nodeId"], "selector": "#paper-load"})
    session.call("DOM.setFileInputFiles", {"files": [str(temp / "answers.html")], "nodeId": node["nodeId"]})
    session.wait_until("document.documentElement.getAttribute('data-paper-status') === 'finished'", 5)
    checks.run("B3", [
        (page.checked("input[name='q1'][value='A']"), "radio q1 A is not checked"),
        (page.value("#q3") == "Rain fell all day.", f"q3 is {page.value('#q3')!r}"),
        (not page.visible("#paper-load-error"), "#paper-load-error is visible"),
    ])

    session.navigate(url_c)
    checks.run("B4", [
        (page.status() == "invalid", f"status is {page.status()!r}, not invalid"),
        (page.visible("#paper-runtime-error"), "#paper-runtime-error is not visible"),
        (len(page.visible_questions()) == 5, f"visible questions are {page.visible_questions()}"),
        (not page.visible("#paper-clock"), "#paper-clock is visible"),
    ])

    foreign = _foreign_requests(session.events, [url_b, url_c])
    checks.run("B5", [(not foreign, f"requests outside the papers: {foreign}")])
    session.close()


def exercise(browser: str) -> tuple[str, int]:
    checks = Checks()
    sessions: list[Session] = []
    with tempfile.TemporaryDirectory(prefix="paper-runtime-", ignore_cleanup_errors=True) as temporary:
        temp = Path(temporary)
        downloads = temp / "downloads"
        downloads.mkdir()
        try:
            papers = write_papers(temp)

            def open_session(profile: str) -> Session:
                session = Session(browser, temp / profile, downloads)
                sessions.append(session)
                session.connect()
                return session

            product = scenario_a(open_session, papers, temp, checks)
            scenario_b(open_session, papers, temp, checks)
        finally:
            for session in sessions:
                session.close()
    if checks.passed != EXPECTED_CHECKS:
        raise ExerciseError(f"{checks.passed} checks ran, not {EXPECTED_CHECKS}")
    return product, checks.passed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--browser", help="path to a Chrome, Edge, or other Chromium-based browser")
    arguments = parser.parse_args(sys.argv[1:])
    try:
        product, count = exercise(find_browser(arguments.browser))
    except Exception as exc:
        print(f"Paper runtime exercise failed: {exc}", file=sys.stderr)
        return 1
    print(f"Paper runtime exercise passed in {product}: {count} checks.")
    return 0
