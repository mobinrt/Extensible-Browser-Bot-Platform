"""Selenium adapter: normal interaction, read-only widget metadata and network evidence."""
import re
import time

from selenium.common.exceptions import (
    InvalidSelectorException,
    StaleElementReferenceException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from app.core.config import Settings
from app.domain.contracts import BotRunError, RunStatus
from app.infrastructure.browser.diagnostics import Checkpoint
from app.infrastructure.browser.network import ChromeNetworkObserver, Verification

# Read only the named getter registered by the public checkbox.js implementation.
# Do not read getArcToken or infer an ID from a token/create-request query parameter.
WIDGET_ID_SCRIPT = """
const api = window.arcaptcha;
if (!api || !api.widgets) return null;
const roots = document.querySelectorAll('.arcaptcha-vue [data-widget-id], .arcaptcha-vue[data-widget-id]');
for (const root of roots) {
  const id = root.getAttribute('data-widget-id');
  if (!Object.prototype.hasOwnProperty.call(api.widgets, id)) continue;
  const widget = api.widgets[id];
  if (typeof widget.getChallengeID === 'function') {
    const value = widget.getChallengeID();
    if (typeof value === 'string' && value.trim()) return value;
  }
}
return null;
"""


WIDGET_READY_SCRIPT = """
const api = window.arcaptcha;
return !!api && !!api.widgets && [...document.querySelectorAll(
  '.arcaptcha-vue [data-widget-id], .arcaptcha-vue[data-widget-id]'
)].some(root => {
  const id = root.getAttribute('data-widget-id');
  return Object.prototype.hasOwnProperty.call(api.widgets, id) &&
    typeof api.widgets[id].getChallengeID === 'function';
});
"""


def valid_challenge(value: object) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r"[A-Za-z0-9_.:-]{1,256}", value))


class ArcaptchaPage:
    def __init__(self, driver, settings: Settings, checkpoint: Checkpoint | None = None):
        self.driver = driver
        self.s = settings
        self.checkpoint = checkpoint
        self.network = ChromeNetworkObserver(driver, settings.demo_url, checkpoint=self._network_checkpoint if checkpoint else None)
        self.challenge_source = ""
        self._submitted = False
        self.checkbox_clicked = False
        self.widget_loaded: bool | None = None
        self.checkbox_exists: bool | None = None
        self.site_rejection = False
        self.stage = "browser"
        self._stage_started = time.monotonic()
        self._seen: set[str] = set()

    def _network_checkpoint(self, name: str, details: dict) -> None:
        if self.checkpoint:
            self.checkpoint(name, {"stage": self.stage, **details})

    def _stage(self, name: str) -> None:
        if name != self.stage:
            self.stage = name
            self._stage_started = time.monotonic()

    def _emit(self, name: str, **details) -> None:
        if self.checkpoint and name not in self._seen:
            self._seen.add(name)
            self.checkpoint(name, {"stage": self.stage,
                "stage_duration_ms": round((time.monotonic() - self._stage_started) * 1000, 3),
                "checkbox_clicked": self.checkbox_clicked, "checkbox_exists": self.checkbox_exists,
                "widget_loaded": self.widget_loaded, "site_rejection": self.site_rejection, **details})

    def _element(self, selector: str, *, clickable: bool = False):
        if selector:
            for element in self.driver.find_elements(By.CSS_SELECTOR, selector):
                if not clickable or (element.is_displayed() and element.is_enabled()):
                    return element
        return None

    def _wait(self, action):
        return WebDriverWait(self.driver, self.s.selenium_wait_seconds,
                             ignored_exceptions=(StaleElementReferenceException,)).until(lambda _: action())

    def open(self) -> None:
        self._stage("navigation")
        self._emit("PAGE_NAVIGATION_STARTED")
        self.network.start()  # before navigation and checkbox: capture manual submissions too
        try:
            self.driver.get(self.s.demo_url)
            self.network.bind_document()
            self.checkbox_exists = bool(self.driver.find_elements(By.CSS_SELECTOR, "#arc-checkbox, #ar-checkbox"))
            self.widget_loaded = self.driver.execute_script(WIDGET_READY_SCRIPT) is True
            self._emit("PAGE_LOADED", url=self.driver.current_url,
                       ready_state=self.driver.execute_script("return document.readyState"),
                       network_observer_available=self.network.available)
            self._stage("widget_initialization")
            self.network.poll()
            self.raise_if_blocked()
        except TimeoutException as error:
            raise BotRunError("NAVIGATION_TIMEOUT", "navigation", RunStatus.TIMED_OUT) from error
        except WebDriverException as error:
            raise BotRunError("NAVIGATION_FAILED", "navigation") from error

    def raise_environment_error(self) -> None:
        self.raise_if_blocked()  # explicit widget rejection takes precedence over transport symptoms
        if self.network.resource_failures:
            raise BotRunError("CAPTCHA_NETWORK_ERROR", self.stage)
        for element in self.driver.find_elements(By.CSS_SELECTOR, ".arcaptcha-vue .arc-widget-error"):
            if element.is_displayed() and isinstance(element.text, str) and element.text.strip():
                raise BotRunError("CAPTCHA_WIDGET_ERROR", self.stage)

    def wait_for_widget(self) -> None:
        self._stage("widget_initialization")
        def ready():
            self.network.poll()
            self.raise_if_blocked()
            self.checkbox_exists = bool(self.driver.find_elements(By.CSS_SELECTOR, self.s.arcaptcha_checkbox_selector))
            self.widget_loaded = self.driver.execute_script(WIDGET_READY_SCRIPT) is True
            if self.widget_loaded:
                self._emit("WIDGET_DETECTED")
            element = self._element(self.s.arcaptcha_checkbox_selector, clickable=True)
            if element is not None:
                self._emit("CHECKBOX_LOCATED")
            return self.widget_loaded and element is not None
        try:
            self._wait(ready)
        except InvalidSelectorException as error:
            raise BotRunError("CHECKBOX_SELECTOR_INVALID", "checkbox") from error
        except TimeoutException as error:
            self.raise_environment_error()
            code = "CHECKBOX_TIMEOUT" if self.widget_loaded else "WIDGET_NOT_READY"
            raise BotRunError(code, "checkbox" if self.widget_loaded else "widget_initialization", RunStatus.TIMED_OUT) from error

    def click_checkbox(self) -> None:
        if self.checkbox_clicked:
            return
        self.wait_for_widget()
        self._stage("before_checkbox")
        def click():
            self.network.poll()
            self.raise_if_blocked()  # no click if the page already rejected the session
            element = self._element(self.s.arcaptcha_checkbox_selector, clickable=True)
            if element is None:
                return False
            self._emit("BEFORE_CHECKBOX_CLICK")
            element.click()
            self.checkbox_clicked = True
            self._stage("checkbox")
            self._emit("AFTER_CHECKBOX_CLICK")
            return True
        try:
            self._wait(click)
            self._stage("challenge_creation")
            self.network.poll()
            self.raise_if_blocked()
        except TimeoutException as error:
            raise BotRunError("CHECKBOX_TIMEOUT", "checkbox", RunStatus.TIMED_OUT) from error
        except WebDriverException as error:
            raise BotRunError("CHECKBOX_INTERACTION_FAILED", "checkbox") from error

    def read_challenge_id(self) -> str | None:
        self._stage("challenge_creation")
        def read():
            self.network.poll()
            value = self.driver.execute_script(WIDGET_ID_SCRIPT)
            if valid_challenge(value):
                self.challenge_source = "widget_getChallengeID"
                self._emit("CHALLENGE_ID_OBSERVED")
                return value
            # Explicitly named semantic DOM sources only. Legacy arbitrary CSS is ignored.
            for element in self.driver.find_elements(
                    By.CSS_SELECTOR, "[data-challenge-id], input[name='challenge_id']"):
                value = element.get_attribute("data-challenge-id") or element.get_attribute("value")
                if valid_challenge(value):
                    self.challenge_source = "named_dom_challenge_id"
                    self._emit("CHALLENGE_ID_OBSERVED")
                    return value
            self.raise_if_blocked()
            return False
        try:
            return self._wait(read)
        except TimeoutException:
            self.raise_environment_error()
            return None

    def fill_credentials(self, username: str, password: str) -> None:
        self._stage("credentials")
        if not username or not password:
            raise BotRunError("CREDENTIALS_NOT_CONFIGURED", "credentials")
        def fill():
            user = self._element(self.s.arcaptcha_username_selector, clickable=True)
            secret = self._element(self.s.arcaptcha_password_selector, clickable=True)
            if user is None or secret is None:
                return False
            user.clear()
            user.send_keys(username)
            secret.clear()
            secret.send_keys(password)
            return True
        try:
            self._wait(fill)
        except TimeoutException as error:
            raise BotRunError("CREDENTIAL_FIELDS_NOT_FOUND", "credentials") from error
        except WebDriverException as error:
            raise BotRunError("CREDENTIAL_ENTRY_FAILED", "credentials") from error

    def is_solved(self) -> bool:
        try:
            token = self._element("#arcaptcha-token")
            # Hidden checkbox selection is legitimate DOM state; visibility is irrelevant.
            checked = self._element(".arcaptcha-vue #input-checkbox input[type='checkbox']")
            solved = bool(token and token.get_attribute("value") and checked and checked.is_selected())
            if solved:
                self._emit("CAPTCHA_SOLVED")
            return solved
        except StaleElementReferenceException:
            return False

    def raise_if_blocked(self) -> None:
        for error in self.driver.find_elements(By.CSS_SELECTOR, ".arcaptcha-vue .arc-widget-error"):
            text = error.text
            if (isinstance(text, str) and error.is_displayed()
                    and text.strip().startswith(("Blocked!", "بلاک!"))):
                self.site_rejection = True
                self._emit("SITE_BLOCK_DETECTED")
                raise BotRunError("CAPTCHA_SITE_BLOCKED", "captcha", RunStatus.BLOCKED)

    def wait_for_solved(self) -> bool:
        self._stage("captcha")
        def ready():
            self.raise_if_blocked()
            return self.submission_observed() or self.is_solved()
        try:
            return bool(self._wait(ready))
        except TimeoutException:
            return False

    def verification_result(self) -> Verification:
        self._stage("verification")
        return self.network.poll()

    def submission_observed(self) -> bool:
        return self._submitted or self.network.submitted

    def submit(self) -> None:
        self._stage("submission")
        if self.submission_observed():
            return
        if not self.is_solved():
            raise BotRunError("CAPTCHA_NOT_READY", "submission", RunStatus.BLOCKED)
        if not self.network.available:
            raise BotRunError("NETWORK_OBSERVER_UNAVAILABLE", "verification", RunStatus.BLOCKED)
        def click():
            element = self._element(self.s.arcaptcha_submit_selector, clickable=True)
            if element is None:
                return False
            # Never retry a click after dispatch; a transport error has ambiguous effects.
            self._submitted = True
            try:
                element.click()
            except WebDriverException as error:
                raise BotRunError("FORM_SUBMISSION_FAILED", "submission") from error
            return True
        try:
            self._wait(click)
        except TimeoutException as error:
            raise BotRunError("SUBMIT_NOT_FOUND", "submission") from error
        except WebDriverException as error:
            raise BotRunError("FORM_SUBMISSION_FAILED", "submission") from error

    def close(self) -> None:
        self.network.poll()
        self.network.close()
