import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.domain.contracts import BotRunError, BrowserMode
from app.infrastructure.browser import undetected_factory as module


@pytest.fixture
def launch(monkeypatch, tmp_path):
    chrome = tmp_path / "chrome"
    source = tmp_path / "driver"
    chrome.write_bytes(b"chrome")
    source.write_bytes(b"unmodified original driver")
    driver = Mock()
    constructor = Mock(return_value=driver)
    options = Mock()
    monkeypatch.setitem(sys.modules, "undetected_chromedriver", SimpleNamespace(
        Chrome=constructor, ChromeOptions=Mock(return_value=options)))
    monkeypatch.setattr(module.subprocess, "run", lambda *a, **k: SimpleNamespace(
        stdout="ChromeDriver 155.0.8059.79"))
    monkeypatch.setattr(module, "_owned_processes", lambda *_: [])
    return module.UndetectedChromeFactory(chrome, source), constructor, driver, source


@pytest.mark.parametrize("mode", [BrowserMode.HEADFUL, BrowserMode.HEADLESS])
def test_private_driver_copy_and_profile_are_removed_on_quit(launch, mode):
    factory, constructor, raw, source = launch
    owned = factory.start(mode)
    kwargs = constructor.call_args.kwargs
    copied = Path(kwargs["driver_executable_path"])
    assert copied != source and copied.read_bytes() == source.read_bytes()
    assert kwargs["headless"] is (mode is BrowserMode.HEADLESS)
    assert kwargs["no_sandbox"] is False
    assert kwargs["version_main"] == 155
    assert owned.execute_cdp_cmd is raw.execute_cdp_cmd
    owned.quit()
    owned.quit()
    assert not copied.parent.exists()
    assert source.read_bytes() == b"unmodified original driver"
    raw.quit.assert_called_once()


def test_setup_failure_closes_returned_driver_and_removes_copy(launch):
    factory, constructor, raw, source = launch
    raw.set_page_load_timeout.side_effect = RuntimeError("setup failed")
    with pytest.raises(RuntimeError, match="setup failed"):
        factory.start(BrowserMode.HEADFUL)
    raw.quit.assert_called_once()
    assert not Path(constructor.call_args.kwargs["driver_executable_path"]).exists()
    assert source.exists()


def test_constructor_failure_removes_owned_workspace(launch):
    factory, constructor, _, _ = launch
    constructor.side_effect = RuntimeError("launch failed")
    with pytest.raises(RuntimeError, match="launch failed"):
        factory.start(BrowserMode.HEADFUL)
    assert not Path(constructor.call_args.kwargs["driver_executable_path"]).parent.exists()


def test_quit_failure_still_removes_workspace(launch):
    factory, constructor, raw, _ = launch
    owned = factory.start(BrowserMode.HEADFUL)
    raw.quit.side_effect = RuntimeError("quit failed")
    with pytest.raises(RuntimeError, match="quit failed"):
        owned.quit()
    assert not Path(constructor.call_args.kwargs["driver_executable_path"]).parent.exists()


def test_missing_local_executables_fail_without_downloading(tmp_path):
    with pytest.raises(BotRunError, match="UC_EXECUTABLE_UNAVAILABLE"):
        module.UndetectedChromeFactory(tmp_path / "missing", tmp_path / "driver").start(
            BrowserMode.HEADFUL)
