"""Opt-in, allowlisted local evidence. Never serialize raw browser/network objects."""
from __future__ import annotations

import json
import logging
import math
import os
import re
import socket
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit
from urllib.request import urlopen
from uuid import UUID

import selenium
from selenium.common.exceptions import WebDriverException
from urllib3.exceptions import HTTPError

Checkpoint = Callable[[str, dict[str, Any]], None]
HOSTS = frozenset({"demo.arcaptcha.co", "widget.arcaptcha.ir", "api.arcaptcha.ir"})
STAGES = frozenset({"browser", "navigation", "widget_initialization", "before_checkbox",
                    "checkbox", "challenge_creation", "captcha", "credentials", "submission",
                    "verification", "worker", "observation", "cleanup"})
EVENTS = frozenset({"BROWSER_CREATED", "PAGE_NAVIGATION_STARTED", "PAGE_LOADED", "WIDGET_DETECTED",
                    "CHECKBOX_LOCATED", "BEFORE_CHECKBOX_CLICK", "AFTER_CHECKBOX_CLICK",
                    "CHALLENGE_REQUEST_OBSERVED", "CHALLENGE_ID_OBSERVED", "CAPTCHA_SOLVED",
                    "SITE_BLOCK_DETECTED", "LOGIN_SUBMITTED", "LOGIN_RESPONSE_OBSERVED",
                    "RUN_FINISHED", "NETWORK_REQUEST", "NETWORK_RESPONSE", "NETWORK_FAILURE",
                    "CONSOLE_ERROR", "BROWSER_SNAPSHOT", "DIAGNOSTIC_WARNING"})
OUTCOMES = frozenset({"QUEUED", "RUNNING", "WAITING_FOR_HUMAN", "SUCCEEDED", "FAILED", "BLOCKED",
                      "TIMED_OUT", "SITE_REJECTION", "NETWORK_ERROR", "WIDGET_ERROR", "SELENIUM_ERROR",
                      "TIMEOUT", "NO_REJECTION_OBSERVED"})
ENDPOINTS = frozenset({"document", "widget_script", "asset", "challenge_create", "challenge_answer",
                       "login", "other_resource"})
ERRORS = frozenset({"ERR_NAME_NOT_RESOLVED", "ERR_CONNECTION_REFUSED", "ERR_CONNECTION_RESET",
                    "ERR_CONNECTION_CLOSED", "ERR_CONNECTION_TIMED_OUT", "ERR_TIMED_OUT",
                    "ERR_CERT_AUTHORITY_INVALID", "ERR_CERT_DATE_INVALID", "ERR_SSL_PROTOCOL_ERROR",
                    "ERR_FAILED", "ERR_ABORTED", "ERR_BLOCKED_BY_CLIENT", "ERR_NETWORK_CHANGED",
                    "ERR_INTERNET_DISCONNECTED", "ERR_HTTP2_PROTOCOL_ERROR", "ERR_TUNNEL_CONNECTION_FAILED"})


def allowed(value: object, choices: frozenset | set) -> bool:
    return isinstance(value, str) and value in choices


def safe_url(value: object) -> str:
    """Drop user info, queries, fragments and unrecognized/dynamic paths."""
    if not isinstance(value, str):
        return "[redacted]"
    try:
        u = urlsplit(value)
        if u.scheme not in {"http", "https"} or u.hostname not in HOSTS:
            return "[external-or-local-resource]"
        path = u.path
        if path not in {"", "/", "/api/login", "/arcaptcha/api/create", "/arcaptcha/api/answer", "/1/api.js"}:
            path = "/[redacted-resource]"
        return f"{u.scheme}://{u.hostname}{path}"
    except ValueError:
        return "[redacted]"


def version_number(value: object) -> str:
    match = re.match(r"\d+(?:\.\d+){1,4}", value) if isinstance(value, str) else None
    return match.group() if match else "unknown"


def network_error(value: object) -> str:
    if isinstance(value, str):
        for code in ERRORS:
            if re.search(r"\b" + code + r"\b", value):
                return code
    return "UNSPECIFIED_NETWORK_ERROR"


def console_details(entry: dict) -> dict:
    # Free-form JS output can include tokens/fingerprints, including non-URL strings.
    # Preserve only error taxonomy and a safe source URL, never message text.
    message = entry.get("message", "")
    message = message if isinstance(message, str) else ""
    error_class = next((name for name in ("TypeError", "ReferenceError", "SyntaxError", "RangeError")
                        if name in message), "REDACTED_CONSOLE_ERROR")
    urls = re.findall(r"https?://[^\s\"']+", message)
    return {"error_class": error_class, "network_error": network_error(message),
            "url": safe_url(urls[0]) if urls else "[redacted]",
            "level": entry.get("level") if entry.get("level") in {"SEVERE", "WARNING"} else "SEVERE"}


def grid_version(url: str) -> str:
    try:
        u = urlsplit(url)
        with urlopen(f"{u.scheme}://{u.netloc}/status", timeout=3) as response:
            data = json.loads(response.read(262144))
        versions = [version_number(n.get("version")) for n in data.get("value", {}).get("nodes", [])]
        return versions[0] if versions else "unknown"
    except (OSError, ValueError, TypeError, AttributeError):
        return "unknown"


def dns_result(host: str) -> dict:
    result: dict[str, Any] = {"host": host, "resolved": False}
    done = threading.Event()

    def lookup() -> None:
        try:
            infos = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
            result.update(resolved=True, addresses=sorted({i[4][0] for i in infos})[:8])
        except OSError:
            result["error"] = "DNS_LOOKUP_FAILED"
        finally:
            done.set()
    threading.Thread(target=lookup, daemon=True).start()
    if not done.wait(2):
        return {"host": host, "resolved": False, "error": "DNS_LOOKUP_TIMEOUT"}
    return dict(result)


class RunDiagnostics:
    def __init__(self, directory: Path, run_id: UUID, mode: str):
        self.run_id, self.mode = str(run_id), mode
        self.started = time.monotonic()
        self.wall_started = time.time()
        self.path = directory / f"{run_id}.jsonl"
        self.driver: Any = None
        self.seq = 0
        self.dropped = 0
        self.stage = "browser"
        self.browser = "unknown"
        self.version = "unknown"
        self._file = None
        try:
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            self._file = os.fdopen(fd, "w", encoding="utf-8")
        except OSError:
            logging.getLogger("worker").warning("arcaptcha_diagnostics_artifact_unavailable")

    def browser_created(self, driver, selenium_url: str) -> None:
        self.driver = driver
        caps = driver.capabilities
        self.browser = caps.get("browserName") if caps.get("browserName") in {"chrome", "chromium", "firefox", "msedge"} else "unknown"
        self.version = version_number(caps.get("browserVersion"))
        chrome = caps.get("chrome", {})
        driver_version = version_number(chrome.get("chromedriverVersion"))
        flags = []
        try:
            args = driver.execute_cdp_cmd("Browser.getBrowserCommandLine", {}).get("arguments", [])
            allowed = {"--enable-automation", "--headless", "--window-size", "--no-sandbox",
                       "--disable-dev-shm-usage", "--disable-gpu", "--disable-web-security",
                       "--ignore-certificate-errors", "--proxy-server", "--proxy-pac-url"}
            flags = sorted({arg.split("=", 1)[0] for arg in args if isinstance(arg, str) and arg.split("=", 1)[0] in allowed})
        except (WebDriverException, HTTPError):
            pass
        self.checkpoint("BROWSER_CREATED", {"stage": "browser"})
        # Environment is constructed here from a fixed schema, never serialized caps.
        self._write("ENVIRONMENT", {
            "grid_version": grid_version(selenium_url), "chromedriver_version": driver_version,
            "browser_driver_major_match": driver_version.split(".")[0] == self.version.split(".")[0] if driver_version != "unknown" else None,
            "platform": caps.get("platformName") if caps.get("platformName") in {"linux", "windows", "mac"} else "unknown",
            "page_load_strategy": caps.get("pageLoadStrategy") if caps.get("pageLoadStrategy") in {"normal", "eager", "none"} else "unknown",
            "accept_insecure_certs": caps.get("acceptInsecureCerts") is True,
            "cdp_version": version_number(caps.get("se:cdpVersion")),
            "proxy_configured": bool(caps.get("proxy")) or any(f in flags for f in ["--proxy-server", "--proxy-pac-url"]),
            "proxy_environment_present": any(os.getenv(n) for n in ["HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"]),
            "launch_flag_names": flags, "dns": [dns_result(h) for h in sorted(HOSTS)],
        })

    def _write(self, event: str, details: dict) -> None:
        if self._file is None:
            return
        if self.seq >= 1000 and event != "RUN_FINISHED":
            self.dropped += 1
            return
        self.seq += 1
        now = time.monotonic()
        record = {"schema_version": 1, "run_id": self.run_id, "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                  "elapsed_ms": round((now - self.started) * 1000, 3), "sequence": self.seq,
                  "browser_mode": self.mode, "browser_name": self.browser, "browser_version": self.version,
                  "selenium_version": selenium.__version__, "checkpoint": event, **details}
        try:
            self._file.write(json.dumps(record, ensure_ascii=True) + "\n")
            self._file.flush()
        except OSError:
            try:
                self._file.close()
            except OSError:
                pass
            self._file = None
            logging.getLogger("worker").warning("arcaptcha_diagnostics_write_failed")

    def checkpoint(self, name: str, details: dict[str, Any]) -> None:
        if name not in EVENTS:
            return
        safe: dict[str, Any] = {}
        if allowed(details.get("stage"), STAGES):
            self.stage = details["stage"]
        safe["stage"] = self.stage
        for key in ["checkbox_exists", "widget_loaded", "checkbox_clicked", "site_rejection", "persisted", "network_observer_available"]:
            if type(details.get(key)) is bool:
                safe[key] = details[key]
        for key in ["http_status", "request_index", "stage_duration_ms"]:
            value = details.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and 0 <= value < 10**12:
                safe[key] = value
        if allowed(details.get("endpoint"), ENDPOINTS):
            safe["endpoint"] = details["endpoint"]
        if "url" in details:
            safe["url"] = safe_url(details["url"])
        if allowed(details.get("method"), {"GET", "POST", "OPTIONS", "HEAD"}):
            safe["method"] = details["method"]
        if allowed(details.get("ready_state"), {"loading", "interactive", "complete"}):
            safe["ready_state"] = details["ready_state"]
        if allowed(details.get("outcome"), OUTCOMES):
            safe["outcome"] = details["outcome"]
        if "network_error" in details:
            safe["network_error"] = network_error(details["network_error"])
        if name == "CONSOLE_ERROR":
            for key, choices in {"error_class": {"TypeError", "ReferenceError", "SyntaxError", "RangeError", "REDACTED_CONSOLE_ERROR"},
                                 "level": {"SEVERE", "WARNING"}}.items():
                if isinstance(details.get(key), str) and details.get(key) in choices:
                    safe[key] = details[key]
        wall = details.get("event_wall_time")
        if isinstance(wall, (int, float)) and not isinstance(wall, bool) and math.isfinite(wall) and abs(wall - self.wall_started) < 3600:
            safe["occurred_elapsed_ms"] = round((wall - self.wall_started) * 1000, 3)
        self._write(name, safe)

    def snapshot(self) -> None:
        if self.driver is None:
            return
        try:
            state = self.driver.execute_script("return document.readyState")
            self.checkpoint("BROWSER_SNAPSHOT", {"url": self.driver.current_url, "ready_state": state})
            for entry in self.driver.get_log("browser")[:100]:
                if entry.get("level") in {"SEVERE", "WARNING"}:
                    self.checkpoint("CONSOLE_ERROR", console_details(entry))
        except (WebDriverException, HTTPError):
            self.checkpoint("DIAGNOSTIC_WARNING", {})

    def finish(self, outcome: str, *, persisted: bool = False) -> None:
        self.checkpoint("RUN_FINISHED", {"outcome": outcome, "persisted": persisted})
        if self._file is not None:
            try:
                self._file.close()
            except OSError:
                logging.getLogger("worker").warning("arcaptcha_diagnostics_close_failed")
            self._file = None
