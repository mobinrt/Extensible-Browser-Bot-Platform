from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.bots.arcaptcha import bot as module
from app.domain.contracts import BotContext, BotRunError, BrowserMode, RunStatus
from app.infrastructure.browser.network import Verification, VerificationState


class FakePage:
    def __init__(self, *, challenge="challenge-123", solved=True, observed=True):
        self.challenge = challenge
        self.solved = solved
        self.observed = observed
        self.clicked = False
        self.submitted = False
        self.filled = False
        self.challenge_source = "widget_getChallengeID"
        self.closed = False
        self.manual_submission = False

    def open(self):
        pass

    def click_checkbox(self):
        self.clicked = True

    def read_challenge_id(self):
        return self.challenge

    def fill_credentials(self, username, password):
        assert username == "test_user" and password == "test_pass"
        self.filled = True

    def is_solved(self):
        return self.solved

    def raise_if_blocked(self):
        pass

    def wait_for_solved(self):
        return self.is_solved()

    def submit(self):
        self.submitted = True

    def verification_result(self):
        state = (VerificationState.ACCEPTED if self.observed is True else
                 VerificationState.REJECTED if self.observed is False else VerificationState.PENDING)
        return Verification(state, evidence="browser_login_http_200_expected_msg",
                            code="VERIFICATION_REJECTED")

    def submission_observed(self):
        return self.submitted or self.manual_submission

    def close(self):
        self.closed = True


def run_fake(monkeypatch, page, mode=BrowserMode.HEADLESS, *, expired=False):
    observed = []
    monkeypatch.setattr(module, "make_page", lambda driver, settings, checkpoint=None: page)
    settings = SimpleNamespace(demo_username="test_user",
                               demo_password=SimpleNamespace(get_secret_value=lambda: "test_pass"),
                               selenium_wait_seconds=1, manual_timeout_seconds=1)
    monkeypatch.setattr(module, "get_settings", lambda: settings)

    def check():
        if expired:
            raise BotRunError("RUN_DEADLINE_EXCEEDED", "worker", RunStatus.TIMED_OUT)

    ctx = BotContext(mode=mode, driver=object(),
                     deadline=datetime.now(timezone.utc) + timedelta(seconds=10),
                     record_challenge=observed.append,
                     report_manual_wait=lambda: observed.append("manual"),
                     check_deadline=check,
                     report_running=lambda: observed.append("running"))
    try:
        return module.ArcaptchaBot().run(ctx), observed
    except BotRunError as error:
        return error, observed


def test_verified_success_after_challenge_persistence(monkeypatch):
    page = FakePage()
    result, saved = run_fake(monkeypatch, page)
    assert result.status == RunStatus.SUCCEEDED
    assert saved == ["challenge-123"]
    assert page.filled and page.clicked and page.submitted


def test_missing_challenge_stops_before_credentials(monkeypatch):
    page = FakePage(challenge=None)
    error, saved = run_fake(monkeypatch, page)
    assert error.code == "CHALLENGE_ID_UNAVAILABLE"
    assert not saved and not page.filled and not page.submitted


def test_blocked_headless_cannot_submit(monkeypatch):
    page = FakePage(solved=False)
    error, saved = run_fake(monkeypatch, page)
    assert error.status == RunStatus.BLOCKED
    assert error.code == "CAPTCHA_REQUIRES_HUMAN"
    assert saved == ["challenge-123"] and not page.submitted


def test_negative_verification_is_not_success(monkeypatch):
    error, saved = run_fake(monkeypatch, FakePage(observed=False))
    assert error.status == RunStatus.FAILED
    assert error.code == "VERIFICATION_REJECTED"
    assert saved == ["challenge-123"]


def test_uncertain_verification_is_not_success(monkeypatch):
    ticks = iter([0, 0, 2])
    monkeypatch.setattr(module.time, "monotonic", lambda: next(ticks))
    error, _ = run_fake(monkeypatch, FakePage(observed=None))
    assert error.status == RunStatus.TIMED_OUT
    assert error.code == "VERIFICATION_TIMEOUT"


def test_deadline_exceeded_before_navigation(monkeypatch):
    page = FakePage()
    error, saved = run_fake(monkeypatch, page, expired=True)
    assert error.status == RunStatus.TIMED_OUT and saved == []
    assert not page.clicked


def test_manual_submission_in_flight_is_never_repeated(monkeypatch):
    page = FakePage(solved=False)
    page.manual_submission = True
    result, saved = run_fake(monkeypatch, page, BrowserMode.HEADFUL)
    assert result.status is RunStatus.SUCCEEDED
    assert saved == ["challenge-123"]
    assert not page.submitted and not page.filled and page.closed


def test_manual_completion_resumes_once(monkeypatch):
    page = FakePage(solved=False)
    calls = iter([False, True])
    page.is_solved = lambda: next(calls)
    result, saved = run_fake(monkeypatch, page, BrowserMode.HEADFUL)
    assert saved == ["challenge-123", "manual", "running"]
    assert result.status is RunStatus.SUCCEEDED and page.submitted and page.closed


def test_challenge_commit_precedes_credentials(monkeypatch):
    page = FakePage()
    page.fill_credentials = lambda *_: (_ for _ in ()).throw(BotRunError("CREDENTIAL_ENTRY_FAILED", "credentials"))
    result, saved = run_fake(monkeypatch, page)
    assert result.code == "CREDENTIAL_ENTRY_FAILED" and saved == ["challenge-123"]
    assert page.closed and not page.submitted


def test_challenge_overlay_is_completed_before_typing(monkeypatch):
    page = FakePage(solved=False)
    def complete():
        assert not page.filled
        page.solved = True
        return True
    page.wait_for_solved = complete
    original_fill = page.fill_credentials
    def fill(*args):
        assert page.solved
        original_fill(*args)
    page.fill_credentials = fill
    result, saved = run_fake(monkeypatch, page, BrowserMode.HEADFUL)
    assert saved == ["challenge-123"] and page.filled
    assert result.status is RunStatus.SUCCEEDED
