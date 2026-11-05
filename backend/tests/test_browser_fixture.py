"""Real browser + HTTP fixture. Opt in with SELENIUM_TEST_URL; live tests separate."""
import json
import os
import threading
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from selenium.webdriver.support.ui import WebDriverWait

from app.bots.arcaptcha.page import ArcaptchaPage
from app.domain.contracts import BotContext, BotRunError, BrowserMode, RunStatus
from app.infrastructure.browser.network import VerificationState
from app.infrastructure.browser.selenium_factory import SeleniumBrowserFactory


@pytest.fixture
def driver():
    url = os.getenv("SELENIUM_TEST_URL")
    if not url:
        pytest.skip("requires SELENIUM_TEST_URL")
    mode = BrowserMode(os.getenv("BROWSER_TEST_MODE", "HEADLESS"))
    driver = SeleniumBrowserFactory(url).start(mode)
    try:
        yield driver
    finally:
        driver.quit()


@pytest.fixture
def fixture_site():
    submissions = []
    html = Path(__file__).parent.joinpath("fixtures/arcaptcha_demo.html").read_bytes()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(html.replace(b"__FIXTURE_CHALLENGE_ID__", str(uuid4()).encode()))

        def do_POST(self):
            data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            submissions.append(data["username"])  # no tokens/passwords retained
            username = data["username"]
            status = 200 if username != "wrong" else 403
            body = (b'{"msg":"You are logged in successfully!"}' if username == "demo" else
                    b'{"msg":"Rejected"}' if username in {"wrong", "http200-rejected"} else b'not-json')
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(("0.0.0.0", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host = os.getenv("TEST_FIXTURE_HOST", "127.0.0.1")
    settings = SimpleNamespace(
        demo_url=f"http://{host}:{server.server_port}", selenium_wait_seconds=5,
        arcaptcha_checkbox_selector="#arc-checkbox, #ar-checkbox",
        arcaptcha_username_selector="#email", arcaptcha_password_selector="#password",
        arcaptcha_submit_selector="form button")
    try:
        yield settings, submissions
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.mark.parametrize("username,expected", [
    ("demo", VerificationState.ACCEPTED), ("wrong", VerificationState.REJECTED),
    ("http200-rejected", VerificationState.REJECTED), ("malformed", VerificationState.UNKNOWN),
])
def test_controlled_server_result(driver, fixture_site, username, expected):
    settings, submissions = fixture_site
    page = ArcaptchaPage(driver, settings)
    try:
        page.open()
        assert page.network.available, "Remote CDP/performance logging required"
        page.click_checkbox()
        challenge = page.read_challenge_id()
        assert str(UUID(challenge)) == challenge
        assert page.challenge_source == "widget_getChallengeID"
        page.fill_credentials(username, "demo")
        WebDriverWait(driver, 5).until(lambda _: page.is_solved())
        assert page.verification_result().state is VerificationState.PENDING
        page.submit()
        page.submit()  # guard: must not cause a second HTTP request
        result = WebDriverWait(driver, 5).until(
            lambda _: (v if (v := page.verification_result()).state is not VerificationState.PENDING else False))
        assert result.state is expected
        assert submissions == [username]
    finally:
        page.close()


def test_local_smoke_bot(driver):
    from app.bots.examples.example_bot import ExampleBot
    ctx = BotContext(BrowserMode.HEADLESS, driver, datetime.now(timezone.utc) + timedelta(seconds=20),
                     lambda _: None, lambda: None, lambda: None)
    assert ExampleBot().run(ctx).status is RunStatus.SUCCEEDED


def test_live_demo_opt_in(driver, monkeypatch):
    if os.getenv("RUN_LIVE_DEMO") != "1":
        pytest.skip("requires RUN_LIVE_DEMO=1")
    from app.bots.arcaptcha import bot as bot_module
    from app.core.config import Settings
    settings = Settings(database_url="postgresql://unused")
    monkeypatch.setattr(bot_module, "get_settings", lambda: settings)
    saved = []
    deadline = datetime.now(timezone.utc) + timedelta(seconds=settings.run_timeout_seconds)

    def check():
        if datetime.now(timezone.utc) >= deadline:
            raise BotRunError("RUN_DEADLINE_EXCEEDED", "worker", RunStatus.TIMED_OUT)

    result = bot_module.ArcaptchaBot().run(BotContext(
        BrowserMode(os.getenv("BROWSER_TEST_MODE", "HEADFUL")), driver, deadline,
        saved.append, lambda: None, check))
    assert saved and result.status is RunStatus.SUCCEEDED
    assert result.evidence == "browser_login_http_200_expected_msg"


def test_console_launch_smoke(driver):
    """Opt-in real UI -> API -> queue -> worker -> browser -> UI acceptance."""
    url = os.getenv("UI_TEST_URL")
    if not url:
        pytest.skip("requires UI_TEST_URL and a separate running API/worker/database")
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import Select
    driver.get(url)
    WebDriverWait(driver, 15).until(
        lambda _: driver.find_elements(By.CSS_SELECTOR, '#bot option[value="local-smoke"]'))
    Select(driver.find_element(By.ID, "bot")).select_by_value("local-smoke")
    driver.find_element(By.XPATH, "//button[contains(., 'Start execution')]").click()
    WebDriverWait(driver, 60).until(
        lambda _: driver.find_element(By.CSS_SELECTOR, ".drawer .status").text == "Succeeded")
    assert "observed_local_ready_text" in driver.find_element(By.CSS_SELECTOR, ".drawer .metadata").text
    assert "local-smoke" in driver.find_element(By.CSS_SELECTOR, ".drawer").text
    if path := os.getenv("UI_TEST_SCREENSHOT"):
        driver.save_screenshot(path)
