"""Controlled, opt-in observations; never solve a challenge or submit login."""
import argparse
import json
import time
from uuid import uuid4

from selenium.common.exceptions import TimeoutException, WebDriverException
from urllib3.exceptions import HTTPError

from app.bots.arcaptcha.page import ArcaptchaPage
from app.core.config import Settings, get_settings
from app.domain.contracts import BotRunError, BrowserMode
from app.infrastructure.browser.diagnostics import RunDiagnostics
from app.infrastructure.browser.selenium_factory import SeleniumBrowserFactory
from app.infrastructure.browser.undetected_factory import UndetectedChromeFactory


def classify(error: Exception) -> str:
    if isinstance(error, BotRunError):
        if error.code == "CAPTCHA_SITE_BLOCKED":
            return "SITE_REJECTION"
        if error.code == "CAPTCHA_NETWORK_ERROR":
            return "NETWORK_ERROR"
        if error.code == "CAPTCHA_WIDGET_ERROR":
            return "WIDGET_ERROR"
        if error.status.value == "TIMED_OUT":
            return "TIMEOUT"
        return "SELENIUM_ERROR"
    if isinstance(error, TimeoutException):
        return "TIMEOUT"
    if isinstance(error, HTTPError):
        return "NETWORK_ERROR"
    return "SELENIUM_ERROR"


def observe_case(settings: Settings, mode: BrowserMode, click: bool, seconds: float, case: str) -> dict:
    if not settings.arcaptcha_diagnostics_enabled:
        raise ValueError("ARCAPTCHA_DIAGNOSTICS_ENABLED must be true")
    run_id = uuid4()
    diagnostics = RunDiagnostics(settings.arcaptcha_diagnostics_directory, run_id, str(mode))
    driver = page = None
    outcome = "NO_REJECTION_OBSERVED"
    try:
        factory = (
            UndetectedChromeFactory(settings.chrome_binary, settings.chromedriver_binary)
            if settings.browser_backend == "undetected-chrome"
            else SeleniumBrowserFactory(settings.selenium_url)
        )

        factory.capture_console = True
        driver = factory.start(mode)

        diagnostics.browser_created(
            driver,
            settings.selenium_url,
            settings.browser_backend,
        )
        
        page = ArcaptchaPage(driver, settings, checkpoint=diagnostics.checkpoint)
        page.open()
        page.wait_for_widget()
        if click:
            page.click_checkbox()
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            page.network.poll()
            page.raise_if_blocked()
            if click:
                # One bounded getter observation; no credentials/login in this tool.
                page.read_challenge_id()
                page.is_solved()
                break
            time.sleep(0.25)
        page.raise_environment_error()
    except (BotRunError, TimeoutException, WebDriverException, HTTPError) as error:
        outcome = classify(error)
    finally:
        if page is not None:
            page.close()
        diagnostics.snapshot()
        if driver is not None:
            try:
                driver.quit()
            except (WebDriverException, HTTPError):
                diagnostics.checkpoint("DIAGNOSTIC_WARNING", {"stage": "cleanup"})
        diagnostics.finish(outcome)
    return {"case": case, "run_id": str(run_id), "mode": str(mode), "click_requested": click,
            "checkbox_clicked": page.checkbox_clicked if page else False, "outcome": outcome,
            "artifact": str(diagnostics.path)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=list(BrowserMode), default="HEADLESS")
    parser.add_argument("--no-click", action="store_true")
    parser.add_argument("--compare", action="store_true", help="Four fresh sessions: A/B Headful; C/D Headless, without/with click")
    parser.add_argument("--case", choices=["A", "B", "C", "D"], help="Execute just one comparison case")
    parser.add_argument("--observe-seconds", type=float, default=5)
    args = parser.parse_args()
    if not 1 <= args.observe_seconds <= 30:
        parser.error("--observe-seconds must be between 1 and 30")
    settings = get_settings()
    if not settings.arcaptcha_diagnostics_enabled:
        parser.error("Set ARCAPTCHA_DIAGNOSTICS_ENABLED=true; diagnostics are disabled by default")
    cases = {"A": (BrowserMode.HEADFUL, False), "B": (BrowserMode.HEADFUL, True),
             "C": (BrowserMode.HEADLESS, False), "D": (BrowserMode.HEADLESS, True)}
    selected = cases if args.compare else {args.case: cases[args.case]} if args.case else {
        "single": (BrowserMode(args.mode), not args.no_click)}
    for case, (mode, click) in selected.items():
        print(json.dumps(observe_case(settings, mode, click, args.observe_seconds, case)), flush=True)


if __name__ == "__main__":
    main()
