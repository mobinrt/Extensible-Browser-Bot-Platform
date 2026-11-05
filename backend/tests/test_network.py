import base64
import json

import pytest
from selenium.common.exceptions import WebDriverException

from app.infrastructure.browser.network import ChromeNetworkObserver, VerificationState


class Driver:
    def __init__(self):
        self.events = []
        self.body = {"body": json.dumps({"msg": "You are logged in successfully!"})}
        self.commands = []

    def get_log(self, _):
        events, self.events = self.events, []
        return [{"message": json.dumps({"message": e})} for e in events]

    def execute_cdp_cmd(self, command, args):
        self.commands.append(command)
        if command == "Page.getFrameTree":
            return {"frameTree": {"frame": {"id": "main"}}}
        if command == "Network.getResponseBody":
            if isinstance(self.body, Exception):
                raise self.body
            return self.body
        return {}


def event(method, rid="dynamic-42", **params):
    return {"method": "Network." + method, "params": {"requestId": rid, **params}}


def request(rid="dynamic-42", url="https://demo.arcaptcha.co/api/login", frame="main", method="POST"):
    return event("requestWillBeSent", rid, request={"url": url, "method": method}, frameId=frame)


def observer():
    driver = Driver()
    network = ChromeNetworkObserver(driver, "https://demo.arcaptcha.co")
    driver.events = [request("stale-before-start")]
    network.start()
    network.bind_document()
    return driver, network


def complete(driver, rid="dynamic-42", status=200):
    driver.events += [request(rid), event("responseReceived", rid, response={"status": status}),
                      event("loadingFinished", rid)]


def test_real_body_and_duplicate_events_only_once():
    driver, network = observer()
    complete(driver)
    driver.events += [request(), event("loadingFinished")]
    assert network.poll().state is VerificationState.ACCEPTED
    assert len(network.requests) == 1
    network.poll()
    assert driver.commands.count("Network.getResponseBody") == 1
    network.close()
    assert not network.available and not network.requests
    assert driver.commands[-1] == "Network.disable"


@pytest.mark.parametrize("url,frame,method", [
    ("https://evil.example/api/login", "main", "POST"),
    ("https://demo.arcaptcha.co/api/login-extra", "main", "POST"),
    ("https://demo.arcaptcha.co/api/login?x=1", "main", "POST"),
    ("https://demo.arcaptcha.co/api/login", "other", "POST"),
    ("https://demo.arcaptcha.co/api/login", "main", "GET"),
])
def test_wrong_endpoint_frame_or_method_cannot_verify(url, frame, method):
    driver, network = observer()
    driver.events = [request(url=url, frame=frame, method=method),
                     event("responseReceived", response={"status": 200}), event("loadingFinished")]
    assert network.poll().state is VerificationState.PENDING
    assert not network.submitted


@pytest.mark.parametrize("body,status,state", [
    ({"msg": "You are logged in successfully!"}, 403, VerificationState.REJECTED),
    ({"msg": "Invalid captcha"}, 200, VerificationState.REJECTED),
    ({"success": True}, 200, VerificationState.UNKNOWN),
    ([], 200, VerificationState.UNKNOWN),
    (None, 200, VerificationState.UNKNOWN),
])
def test_http_status_and_application_message_both_required(body, status, state):
    driver, network = observer()
    driver.body = {"body": json.dumps(body)}
    complete(driver, status=status)
    assert network.poll().state is state


@pytest.mark.parametrize("body", [{"body": "not-json"}, {"body": "bad%", "base64Encoded": True},
                                  WebDriverException("unavailable"), {}])
def test_bad_body_fails_closed(body):
    driver, network = observer()
    driver.body = body
    complete(driver)
    assert network.poll().code == "LOGIN_RESPONSE_UNREADABLE"


def test_base64_body():
    driver, network = observer()
    driver.body = {"body": base64.b64encode(driver.body["body"].encode()).decode(), "base64Encoded": True}
    complete(driver)
    assert network.poll().state is VerificationState.ACCEPTED


def test_delayed_body_waits_for_loading_finished():
    driver, network = observer()
    driver.events = [request(), event("responseReceived", response={"status": 200})]
    assert network.poll().state is VerificationState.PENDING and network.submitted
    driver.events = [event("loadingFinished")]
    assert network.poll().state is VerificationState.ACCEPTED


def test_multiple_submissions_and_redirects_are_unknown():
    driver, network = observer()
    complete(driver, "one")
    complete(driver, "two")
    assert network.poll().code == "MULTIPLE_LOGIN_REQUESTS"
    driver, network = observer()
    driver.events = [request(), request(url="https://evil.example"), event("loadingFinished")]
    assert network.poll().code == "LOGIN_NETWORK_FAILED"


def test_create_candidate_is_never_a_challenge_id():
    driver, network = observer()
    driver.events = [request(url="https://api.arcaptcha.ir/arcaptcha/api/create?id=some-uuid")]
    network.poll()
    assert network.create_candidate_observed and not network.requests
    assert network.result.state is VerificationState.PENDING


def test_observer_unavailable_fails_closed():
    driver = Driver()
    driver.execute_cdp_cmd = lambda *_: (_ for _ in ()).throw(WebDriverException())
    network = ChromeNetworkObserver(driver, "https://demo.arcaptcha.co")
    network.start()
    assert network.poll().code == "NETWORK_OBSERVER_UNAVAILABLE"
    network.close()


def test_lost_observer_does_not_retain_old_success():
    driver, network = observer()
    complete(driver)
    assert network.poll().state is VerificationState.ACCEPTED
    driver.get_log = lambda _: (_ for _ in ()).throw(WebDriverException())
    assert network.poll().code == "NETWORK_OBSERVER_LOST"


def test_loading_failure_is_not_rejection_or_success():
    driver, network = observer()
    driver.events = [request(), event("loadingFailed")]
    assert network.poll().code == "LOGIN_NETWORK_FAILED"


def test_cleanup_transport_error_does_not_mask_bot_outcome():
    from urllib3.exceptions import ReadTimeoutError
    driver, network = observer()
    driver.execute_cdp_cmd = lambda *_: (_ for _ in ()).throw(ReadTimeoutError(None, "remote", "timeout"))
    network.close()
    assert not network.available and network.result.code == "NETWORK_OBSERVER_CLOSED"


def test_challenge_http_201_is_metadata_not_success_and_urls_are_sanitized():
    driver = Driver()
    records = []
    network = ChromeNetworkObserver(driver, "https://demo.arcaptcha.co", lambda n, d: records.append((n, d)))
    network.start()
    network.bind_document()
    driver.events = [request(url="https://api.arcaptcha.ir/arcaptcha/api/create?id=secret&site_key=secret"),
                     event("responseReceived", response={"status": 201}), event("loadingFinished")]
    assert network.poll().state is VerificationState.PENDING
    assert [n for n, _ in records] == ["NETWORK_REQUEST", "CHALLENGE_REQUEST_OBSERVED", "NETWORK_RESPONSE"]
    assert records[-1][1]["http_status"] == 201
    assert "secret" not in json.dumps(records)
    assert "Network.getResponseBody" not in driver.commands


def test_login_checkpoint_requires_the_correlated_browser_post():
    driver = Driver()
    records = []
    network = ChromeNetworkObserver(driver, "https://demo.arcaptcha.co", lambda n, d: records.append((n, d)))
    network.start()
    network.bind_document()
    driver.events = [request(frame="wrong-frame")]
    network.poll()
    assert not any(n == "LOGIN_SUBMITTED" for n, _ in records)
    complete(driver, rid="correct-frame")
    network.poll()
    names = [n for n, _ in records]
    assert names.index("LOGIN_SUBMITTED") < names.index("LOGIN_RESPONSE_OBSERVED")
