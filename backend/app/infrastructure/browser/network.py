"""Read-only Chrome network observation through RemoteWebDriver's CDP endpoint.

Selenium 4.31 exposes remote execute_cdp_cmd; its BiDi network API does not
provide a response-body reader. Never retain request bodies, headers or tokens.
"""
import base64
import json
from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import urlsplit

from selenium.common.exceptions import WebDriverException
from urllib3.exceptions import HTTPError

from app.infrastructure.browser.diagnostics import Checkpoint, network_error, safe_url


class VerificationState(StrEnum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class Verification:
    state: VerificationState
    evidence: str = ""
    code: str = ""


class ChromeNetworkObserver:
    def __init__(self, driver, origin: str, checkpoint: Checkpoint | None = None):
        self.driver = driver
        self.origin = origin.rstrip("/")
        self.frame_id: str | None = None
        self.requests: dict[str, dict] = {}
        self.available = False
        self.result = Verification(VerificationState.PENDING)
        self.create_candidate_observed = False
        self.checkpoint = checkpoint
        self.resources: dict[str, dict] = {}
        self.resource_failures: list[str] = []
        self._clock_offset: float | None = None
        self._login_response_emitted = False

    def _observe(self, method: str, p: dict, rid: str) -> None:
        if method == "Network.requestWillBeSent":
            request = p.get("request", {})
            if not isinstance(request, dict):
                return
            u = urlsplit(request.get("url", ""))
            expected = urlsplit(self.origin)
            if u.netloc == expected.netloc and u.path == "/api/login":
                endpoint = "login"
            elif u.hostname in {"api.arcaptcha.ir", "widget.arcaptcha.ir"} and u.path in {"/arcaptcha/api/create", "/arcaptcha/api/answer"}:
                endpoint = "challenge_create" if u.path.endswith("create") else "challenge_answer"
            elif p.get("type") == "Document":
                endpoint = "document"
            elif u.hostname == "widget.arcaptcha.ir" and u.path.endswith(".js"):
                endpoint = "widget_script"
            else:
                endpoint = "asset" if u.hostname in {"demo.arcaptcha.co", "widget.arcaptcha.ir", "api.arcaptcha.ir"} else "other_resource"
            if len(self.resources) >= 500 or rid in self.resources:
                return
            data = {"endpoint": endpoint, "url": safe_url(request.get("url")),
                    "method": request.get("method"), "request_index": len(self.resources) + 1}
            self.resources[rid] = data
            if isinstance(p.get("wallTime"), (float, int)) and isinstance(p.get("timestamp"), (float, int)):
                self._clock_offset = p["wallTime"] - p["timestamp"]
            name = "NETWORK_REQUEST"
        elif rid in self.resources and method in {"Network.responseReceived", "Network.loadingFailed"}:
            data = dict(self.resources[rid])
            if method == "Network.responseReceived":
                data["http_status"] = p.get("response", {}).get("status")
                name = "NETWORK_RESPONSE"
            else:
                code = network_error(p.get("errorText"))
                data["network_error"] = code
                if data["endpoint"] in {"document", "widget_script", "challenge_create", "challenge_answer"}:
                    self.resource_failures.append(code)
                name = "NETWORK_FAILURE"
        else:
            return
        if self._clock_offset is not None and isinstance(p.get("timestamp"), (float, int)):
            data["event_wall_time"] = p["timestamp"] + self._clock_offset
        if self.checkpoint:
            self.checkpoint(name, data)
            if name == "NETWORK_REQUEST" and data["endpoint"] == "challenge_create":
                self.checkpoint("CHALLENGE_REQUEST_OBSERVED", data)

    def start(self) -> None:
        try:
            self.driver.execute_cdp_cmd("Network.enable", {})
            self.driver.get_log("performance")  # discard events preceding this run
            self.available = True
        except (WebDriverException, HTTPError):
            self.result = Verification(VerificationState.UNKNOWN, code="NETWORK_OBSERVER_UNAVAILABLE")

    def bind_document(self) -> None:
        if self.available:
            tree = self.driver.execute_cdp_cmd("Page.getFrameTree", {})
            self.frame_id = tree["frameTree"]["frame"]["id"]

    @property
    def submitted(self) -> bool:
        self.poll()
        return bool(self.requests)

    def poll(self) -> Verification:
        if not self.available:
            return self.result
        try:
            for entry in self.driver.get_log("performance"):
                try:
                    event = json.loads(entry["message"])["message"]
                    method, p = event["method"], event["params"]
                    if not isinstance(p, dict):
                        continue
                    rid = p.get("requestId")
                    if not isinstance(rid, str):
                        continue
                    self._observe(method, p, rid)
                    if method == "Network.requestWillBeSent":
                        request = p["request"]
                        url = urlsplit(request["url"])
                        if (request["method"] == "POST" and url.scheme == "https"
                                and url.hostname == "api.arcaptcha.ir"
                                and url.path == "/arcaptcha/api/create"):
                            # Public widget code calls this bowman_id, NOT challenge_id.
                            self.create_candidate_observed = True
                        expected = urlsplit(self.origin)
                        if (request["method"] == "POST" and url.scheme == expected.scheme
                                and url.netloc == expected.netloc and url.path == "/api/login"
                                and not url.query and p.get("frameId") == self.frame_id
                                and self.frame_id is not None):
                            if rid not in self.requests and self.checkpoint:
                                self.checkpoint("LOGIN_SUBMITTED", {"stage": "submission"})
                            self.requests.setdefault(rid, {})
                        elif rid in self.requests:
                            self.requests[rid]["redirected"] = True
                        if rid in self.requests and "redirectResponse" in p:
                            self.requests[rid]["redirected"] = True
                    elif rid in self.requests:
                        item = self.requests[rid]
                        if method == "Network.responseReceived":
                            item["status"] = p["response"]["status"]
                        elif method == "Network.loadingFinished":
                            item["finished"] = True
                        elif method == "Network.loadingFailed":
                            item["failed"] = True
                except (KeyError, TypeError, ValueError):
                    continue  # unrelated/malformed log entries are never evidence
            if len(self.requests) > 1:
                self.result = Verification(VerificationState.UNKNOWN, code="MULTIPLE_LOGIN_REQUESTS")
                return self.result
            for rid, item in self.requests.items():
                if item.get("redirected") or item.get("failed"):
                    self.result = Verification(VerificationState.UNKNOWN, code="LOGIN_NETWORK_FAILED")
                elif item.get("finished") and not item.get("parsed"):
                    item["parsed"] = True
                    try:
                        raw = self.driver.execute_cdp_cmd("Network.getResponseBody", {"requestId": rid})
                        body = raw["body"]
                        if raw.get("base64Encoded"):
                            body = base64.b64decode(body, validate=True).decode("utf-8")
                        data = json.loads(body) if len(body) <= 65536 else None
                        status = item.get("status", 0)
                        if (status == 200 and isinstance(data, dict)
                                and data.get("msg") == "You are logged in successfully!"):
                            self.result = Verification(VerificationState.ACCEPTED,
                                                       evidence="browser_login_http_200_expected_msg")
                        elif isinstance(data, dict) and isinstance(data.get("msg"), str):
                            self.result = Verification(VerificationState.REJECTED,
                                                       code="VERIFICATION_REJECTED")
                        else:
                            self.result = Verification(VerificationState.UNKNOWN,
                                                       code="LOGIN_RESPONSE_UNRECOGNIZED")
                    except (WebDriverException, HTTPError, ValueError, KeyError, UnicodeError, TypeError):
                        self.result = Verification(VerificationState.UNKNOWN,
                                                   code="LOGIN_RESPONSE_UNREADABLE")
        except (WebDriverException, HTTPError):
            self.available = False
            self.result = Verification(VerificationState.UNKNOWN, code="NETWORK_OBSERVER_LOST")
        if self.checkpoint and not self._login_response_emitted:
            for item in self.requests.values():
                if item.get("parsed") and isinstance(item.get("status"), (int, float)):
                    self.checkpoint("LOGIN_RESPONSE_OBSERVED", {"http_status": item.get("status"), "stage": "verification"})
                    self._login_response_emitted = True
        return self.result

    def close(self) -> None:
        self.requests.clear()
        self.resources.clear()
        if self.available:
            try:
                self.driver.execute_cdp_cmd("Network.disable", {})
            except (WebDriverException, HTTPError):
                pass  # driver.quit remains the worker's final cleanup boundary
        self.available = False
        self.result = Verification(VerificationState.UNKNOWN, code="NETWORK_OBSERVER_CLOSED")
