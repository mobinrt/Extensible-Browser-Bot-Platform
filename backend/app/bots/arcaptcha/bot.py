import time
from datetime import datetime, timezone

from app.core.config import get_settings
from app.domain.contracts import (
    BotContext,
    BotDescriptor,
    BotResult,
    BotRunError,
    BrowserMode,
    RunStatus,
)
from app.infrastructure.browser.network import Verification, VerificationState


def make_page(driver, settings, checkpoint=None):
    from app.bots.arcaptcha.page import ArcaptchaPage
    return ArcaptchaPage(driver, settings, checkpoint=checkpoint)


def final_result(outcome: Verification) -> BotResult | None:
    if outcome.state is VerificationState.ACCEPTED:
        return BotResult(RunStatus.SUCCEEDED, evidence=outcome.evidence)
    if outcome.state is VerificationState.REJECTED:
        raise BotRunError(outcome.code, "verification")
    if outcome.state is VerificationState.UNKNOWN:
        raise BotRunError(outcome.code, "verification", RunStatus.BLOCKED)
    return None


class ArcaptchaBot:
    descriptor = BotDescriptor(
        bot_id="arcaptcha-demo", name="Arcaptcha Demo",
        description="Click demo checkbox, record a real challenge ID and verify the form result.",
        requires_credentials=True)

    def run(self, ctx: BotContext) -> BotResult:
        settings = get_settings()
        page = make_page(ctx.driver, settings, ctx.record_checkpoint)
        try:
            ctx.check_deadline()
            page.open()
            ctx.check_deadline()
            page.click_checkbox()
            ctx.check_deadline()
            challenge_id = page.read_challenge_id()
            if not challenge_id:
                raise BotRunError("CHALLENGE_ID_UNAVAILABLE", "challenge")
            ctx.record_challenge(challenge_id)  # independent commit BEFORE later steps
            ctx.check_deadline()
            if not page.submission_observed():
                page.fill_credentials(settings.demo_username, settings.demo_password.get_secret_value())
            if not page.wait_for_solved() and not page.submission_observed():
                if ctx.mode is BrowserMode.HEADLESS:
                    raise BotRunError("CAPTCHA_REQUIRES_HUMAN", "captcha", RunStatus.BLOCKED)
                ctx.report_manual_wait()
                remaining = max(0, (ctx.deadline - datetime.now(timezone.utc)).total_seconds())
                end = time.monotonic() + min(settings.manual_timeout_seconds, remaining)
                while time.monotonic() < end:
                    ctx.check_deadline()
                    page.raise_if_blocked()
                    if page.submission_observed() or page.is_solved():
                        break
                    time.sleep(0.25)  # bounded human state polling
                else:
                    raise BotRunError("MANUAL_CHALLENGE_INCOMPLETE", "captcha", RunStatus.TIMED_OUT)
                ctx.report_running()
            ctx.check_deadline()
            if not page.submission_observed():
                page.submit()
            end = time.monotonic() + settings.selenium_wait_seconds
            while time.monotonic() < end:
                ctx.check_deadline()
                result = final_result(page.verification_result())
                if result:
                    return BotResult(result.status, result.evidence,
                                     {"challenge_source": page.challenge_source})
                time.sleep(0.25)
            raise BotRunError("VERIFICATION_TIMEOUT", "verification", RunStatus.TIMED_OUT)
        finally:
            page.close()
