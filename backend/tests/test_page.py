from unittest.mock import Mock

import pytest
from selenium.common.exceptions import (
    StaleElementReferenceException,
    TimeoutException,
    WebDriverException,
)

from app.bots.arcaptcha.page import ArcaptchaPage, valid_challenge
from app.core.config import Settings
from app.domain.contracts import BotRunError


@pytest.fixture
def page():
    driver = Mock()
    driver.find_elements.return_value = []
    driver.execute_script.return_value = None
    p = ArcaptchaPage(driver, Settings(_env_file=None, database_url="postgresql://unused"))
    p.network = Mock()
    p.network.available = True
    p.network.submitted = False
    p.network.resource_failures = []
    p._wait = lambda fn: fn() or (_ for _ in ()).throw(TimeoutException())
    return p


def test_hidden_token_and_checkbox_state(page):
    token, checkbox = Mock(), Mock()
    token.get_attribute.return_value = "runtime-token"
    checkbox.is_selected.return_value = True
    page.driver.find_elements.side_effect = [[token], [checkbox]]
    assert page.is_solved()
    token.is_displayed.assert_not_called()
    checkbox.is_displayed.assert_not_called()


@pytest.mark.parametrize("value,selected", [("", True), ("runtime-token", False)])
def test_token_alone_and_empty_token_never_solved(page, value, selected):
    token, checkbox = Mock(), Mock()
    token.get_attribute.return_value = value
    checkbox.is_selected.return_value = selected
    page.driver.find_elements.side_effect = [[token], [checkbox]]
    assert not page.is_solved()


def test_checkbox_targets_verified_wrapper(page):
    wrapper = Mock()
    page.driver.execute_script.return_value = True
    page.driver.find_elements.return_value = [wrapper]
    page.click_checkbox()
    wrapper.click.assert_called_once()
    assert any(c.args[1] == "#arc-checkbox, #ar-checkbox" for c in page.driver.find_elements.call_args_list)


def test_missing_checkbox_has_stage_and_timeout(page):
    page.driver.execute_script.return_value = True
    with pytest.raises(BotRunError) as exc:
        page.click_checkbox()
    assert exc.value.code == "CHECKBOX_TIMEOUT"
    assert exc.value.stage == "checkbox"


def test_named_getter_is_authoritative_not_hidden_token(page):
    page.driver.execute_script.return_value = "new-challenge-42"
    assert page.read_challenge_id() == "new-challenge-42"
    assert page.challenge_source == "widget_getChallengeID"


def test_named_hidden_challenge_fallback(page):
    element = Mock()
    element.get_attribute.side_effect = [None, "real-challenge"]
    page.driver.find_elements.return_value = [element]
    assert page.read_challenge_id() == "real-challenge"
    element.is_displayed.assert_not_called()
    assert page.challenge_source == "named_dom_challenge_id"


@pytest.mark.parametrize("value", [None, "", "x"*257, " token with spaces ", "<markup>", 42])
def test_invalid_challenge_identifiers(value):
    assert not valid_challenge(value)


def test_missing_challenge_is_not_invented(page):
    assert page.read_challenge_id() is None


def test_credentials_accept_demo_despite_email_type(page):
    user, secret = Mock(), Mock()
    page.driver.find_elements.side_effect = [[user], [secret]]
    page.fill_credentials("demo", "demo")
    user.send_keys.assert_called_once_with("demo")
    secret.send_keys.assert_called_once_with("demo")


def test_missing_credentials(page):
    with pytest.raises(BotRunError, match="CREDENTIALS_NOT_CONFIGURED"):
        page.fill_credentials("", "")


def test_missing_submit(page):
    page.is_solved = lambda: True
    with pytest.raises(BotRunError, match="SUBMIT_NOT_FOUND"):
        page.submit()


def test_ambiguous_submit_click_is_never_repeated(page):
    button = Mock()
    button.click.side_effect = WebDriverException()
    page.driver.find_elements.return_value = [button]
    page.is_solved = lambda: True
    with pytest.raises(BotRunError, match="FORM_SUBMISSION_FAILED"):
        page.submit()
    page.submit()
    button.click.assert_called_once()


def test_stale_checkbox_click_not_retried_after_dispatch(page):
    button = Mock()
    button.click.side_effect = StaleElementReferenceException()
    page.driver.find_elements.return_value = [button]
    page.is_solved = lambda: True
    with pytest.raises(BotRunError):
        page.submit()
    assert page._submitted


def test_explicit_site_block_is_blocked_even_before_id_exists(page):
    error = Mock()
    error.text = "Blocked! Are you robot? Please refresh the page and try again"
    page.driver.find_elements.side_effect = [[], [error]]
    with pytest.raises(BotRunError, match="CAPTCHA_SITE_BLOCKED") as exc:
        page.read_challenge_id()
    assert exc.value.status.value == "BLOCKED"


def test_obtained_id_is_returned_before_later_block(page):
    page.driver.execute_script.return_value = "server-challenge"
    page.raise_if_blocked = lambda: (_ for _ in ()).throw(BotRunError("CAPTCHA_SITE_BLOCKED", "captcha"))
    assert page.read_challenge_id() == "server-challenge"
