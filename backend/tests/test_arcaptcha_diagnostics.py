import json
from unittest.mock import Mock
from uuid import uuid4

import pytest
from selenium.common.exceptions import (
    InvalidSelectorException,
    TimeoutException,
    WebDriverException,
)

from app.bots.arcaptcha.diagnose import classify
from app.bots.arcaptcha.page import ArcaptchaPage
from app.core.config import Settings
from app.domain.contracts import BotRunError, RunStatus
from app.infrastructure.browser.diagnostics import RunDiagnostics, console_details, safe_url


def settings(**overrides):
    return Settings(_env_file=None, database_url="postgresql://unused", **overrides)


def page_fixture(*, before=False, after=False, ready=True, exists=True):
    driver = Mock()
    state = {"blocked": before}
    box = Mock()
    warning = Mock()
    warning.text = "Blocked! Are you robot? Please refresh the page and try again"
    driver.current_url = "https://demo.arcaptcha.co/?sensitive=never-log"
    driver.execute_script.side_effect = lambda script, *args: "complete" if "document.readyState" in script else ready
    driver.find_elements.side_effect = lambda by, selector: (
        [warning] if state["blocked"] else []
    ) if "arc-widget-error" in selector else ([box] if exists else [])
    box.click.side_effect = lambda: state.update(blocked=after)
    records = []
    page = ArcaptchaPage(driver, settings(), lambda name, data: records.append((name, data)))
    page.network = Mock()
    page.network.resource_failures = []
    page._wait = lambda f: f() or (_ for _ in ()).throw(TimeoutException())
    return driver, box, page, records


def test_block_before_click_stops_without_click_checkpoint():
    _, box, page, records = page_fixture(before=True)
    with pytest.raises(BotRunError, match="CAPTCHA_SITE_BLOCKED"):
        page.open()
    box.click.assert_not_called()
    assert [n for n, _ in records] == ["PAGE_NAVIGATION_STARTED", "PAGE_LOADED", "SITE_BLOCK_DETECTED"]
    assert records[-1][1]["checkbox_clicked"] is False
    assert records[-1][1]["stage"] == "widget_initialization"


def test_block_after_click_is_not_retried():
    _, box, page, records = page_fixture(after=True)
    with pytest.raises(BotRunError, match="CAPTCHA_SITE_BLOCKED"):
        page.click_checkbox()
    page.click_checkbox()
    box.click.assert_called_once()
    names = [n for n, _ in records]
    assert names == ["WIDGET_DETECTED", "CHECKBOX_LOCATED", "BEFORE_CHECKBOX_CLICK", "AFTER_CHECKBOX_CLICK", "SITE_BLOCK_DETECTED"]
    assert records[-1][1]["stage"] == "challenge_creation"
    assert records[-1][1]["checkbox_clicked"] is True


def test_rejection_between_readiness_and_click_is_detected():
    _, box, page, records = page_fixture()
    original = page.wait_for_widget
    def initialize():
        original()
        warning = Mock(text="Blocked! blocked before interaction")
        page.driver.find_elements.side_effect = lambda *_: [warning]
    page.wait_for_widget = initialize
    with pytest.raises(BotRunError, match="CAPTCHA_SITE_BLOCKED"):
        page.click_checkbox()
    box.click.assert_not_called()
    assert not any(n == "BEFORE_CHECKBOX_CLICK" for n, _ in records)


def test_widget_not_ready_never_clicks():
    _, box, page, _ = page_fixture(ready=False)
    with pytest.raises(BotRunError, match="WIDGET_NOT_READY") as error:
        page.click_checkbox()
    assert error.value.status is RunStatus.TIMED_OUT
    box.click.assert_not_called()


def test_incorrect_selector_is_selenium_error_not_site_rejection():
    driver, box, page, _ = page_fixture()
    driver.find_elements.side_effect = InvalidSelectorException()
    with pytest.raises(BotRunError, match="CHECKBOX_SELECTOR_INVALID") as error:
        page.click_checkbox()
    assert classify(error.value) == "SELENIUM_ERROR"
    box.click.assert_not_called()


def test_successful_initialization_does_not_click_in_no_click_case():
    _, box, page, records = page_fixture()
    page.open()
    page.wait_for_widget()
    assert page.widget_loaded and page.checkbox_exists
    assert [n for n, _ in records] == ["PAGE_NAVIGATION_STARTED", "PAGE_LOADED", "WIDGET_DETECTED", "CHECKBOX_LOCATED"]
    box.click.assert_not_called()


def test_network_error_is_not_site_block():
    _, _, page, records = page_fixture(ready=False)
    page.network.resource_failures = ["ERR_NAME_NOT_RESOLVED"]
    with pytest.raises(BotRunError, match="CAPTCHA_NETWORK_ERROR") as error:
        page.wait_for_widget()
    assert classify(error.value) == "NETWORK_ERROR"
    assert not any(n == "SITE_BLOCK_DETECTED" for n, _ in records)


def test_unknown_widget_error_is_not_site_block():
    driver, _, page, records = page_fixture(ready=False)
    warning = Mock(text="Some error just happened")
    driver.find_elements.side_effect = lambda by, selector: [warning] if "arc-widget-error" in selector else []
    with pytest.raises(BotRunError, match="CAPTCHA_WIDGET_ERROR") as error:
        page.wait_for_widget()
    assert classify(error.value) == "WIDGET_ERROR"
    assert not any(n == "SITE_BLOCK_DETECTED" for n, _ in records)


@pytest.mark.parametrize("value", ["https://user:password@demo.arcaptcha.co/api/login?token=secret#cookie",
                                    "https://widget.arcaptcha.ir/arcaptcha/api/images/secret",
                                    "https://secret.example/path?password=secret"])
def test_urls_never_expose_secrets(value):
    assert "password" not in safe_url(value) and "secret" not in safe_url(value)


def test_structured_logs_allowlist_and_permissions(tmp_path):
    run_id = uuid4()
    diag = RunDiagnostics(tmp_path, run_id, "HEADFUL")
    diag.checkpoint("PAGE_LOADED", {"stage": "navigation", "password": "secret", "token": "secret",
                                  "url": "https://demo.arcaptcha.co/?token=secret", "ready_state": "complete"})
    diag.checkpoint("CONSOLE_ERROR", console_details({"level": "SEVERE", "message": 'TypeError token=secret cookie=secret https://demo.arcaptcha.co/?token=secret'}))
    diag.checkpoint("PAGE_LOADED", {"stage": {"password": "secret"}, "ready_state": ["secret"]})
    diag.finish("BLOCKED", persisted=True)
    text = diag.path.read_text()
    assert "secret" not in text and "password" not in text and "cookie" not in text
    rows = [json.loads(line) for line in text.splitlines()]
    assert all(r["run_id"] == str(run_id) and r["timestamp_utc"].endswith("+00:00") for r in rows)
    assert [r["elapsed_ms"] for r in rows] == sorted(r["elapsed_ms"] for r in rows)
    assert rows[-1]["checkpoint"] == "RUN_FINISHED" and rows[-1]["persisted"]
    assert diag.path.stat().st_mode & 0o777 == 0o600


def test_artifact_write_failure_is_observable_but_does_not_change_outcome(tmp_path, caplog):
    invalid = tmp_path / "not-a-directory"
    invalid.write_text("file")
    diag = RunDiagnostics(invalid, uuid4(), "HEADLESS")
    diag.checkpoint("BROWSER_CREATED", {})
    diag.finish("FAILED")
    assert "arcaptcha_diagnostics_artifact_unavailable" in caplog.text


def test_diagnostics_disabled_by_default(tmp_path):
    from app.bots.arcaptcha.diagnose import observe_case
    assert not settings().arcaptcha_diagnostics_enabled
    with pytest.raises(ValueError, match="must be true"):
        observe_case(settings(arcaptcha_diagnostics_directory=tmp_path), "HEADFUL", False, 1, "A")
    assert not list(tmp_path.iterdir())


def test_local_backend_diagnostics_do_not_claim_grid_version(tmp_path, monkeypatch):
    from app.infrastructure.browser import diagnostics as module
    monkeypatch.setattr(module, "grid_version", lambda _: pytest.fail("local UC is not Grid"))
    monkeypatch.setattr(module, "dns_result", lambda host: {"host": host, "resolved": True})
    driver = Mock(capabilities={"browserName": "chrome", "browserVersion": "155.0.8059.79",
                              "chrome": {"chromedriverVersion": "155.0.8059.79"}})
    driver.execute_cdp_cmd.return_value = {"arguments": []}
    diag = RunDiagnostics(tmp_path, uuid4(), "HEADFUL")
    diag.browser_created(driver, "http://unused", "undetected-chrome")
    diag.finish("SUCCEEDED")
    rows = [json.loads(line) for line in diag.path.read_text().splitlines()]
    env = next(row for row in rows if row["checkpoint"] == "ENVIRONMENT")
    assert env["browser_backend"] == "undetected-chrome"
    assert env["grid_version"] == "not_applicable"


@pytest.mark.parametrize("error,outcome", [(TimeoutException(), "TIMEOUT"),
                                            (WebDriverException(), "SELENIUM_ERROR"),
                                            (BotRunError("CAPTCHA_SITE_BLOCKED", "captcha", RunStatus.BLOCKED), "SITE_REJECTION")])
def test_classification(error, outcome):
    assert classify(error) == outcome
