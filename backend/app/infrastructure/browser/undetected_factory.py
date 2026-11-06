"""Optional local Chrome backend. No Grid support; no runtime driver downloads.

Own one fresh profile and driver copy per session. The ordinary Selenium bot and
response-body verifier remain responsible for interaction and final acceptance.
"""
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from app.domain.contracts import BotRunError, BrowserMode


def _owned_processes(profile: Path, driver_copy: Path) -> list[Any]:
    import psutil  # type: ignore[import-not-found, import-untyped]
    result = {}
    for process in psutil.process_iter(["cmdline"]):
        try:
            args = process.info["cmdline"] or []
            if f"--user-data-dir={profile}" in args or str(driver_copy) in args:
                result[process.pid] = process
                for child in process.children(recursive=True):
                    result[child.pid] = child
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return list(result.values())


def _cleanup(directory: tempfile.TemporaryDirectory, profile: Path, driver_copy: Path,
             captured=()) -> None:
    # Match only this session; psutil guards against PID reuse during cleanup.
    processes = {p.pid: p for p in [*captured, *_owned_processes(profile, driver_copy)]}
    if processes:
        import psutil  # type: ignore[import-not-found, import-untyped]
        for process in processes.values():
            try:
                process.terminate()
            except psutil.NoSuchProcess:
                pass
        _, alive = psutil.wait_procs(list(processes.values()), timeout=2)
        for process in alive:
            try:
                process.kill()
            except psutil.NoSuchProcess:
                pass
        psutil.wait_procs(alive, timeout=2)
    end = time.monotonic() + 3
    while True:
        try:
            directory.cleanup()
            break
        except OSError:
            if time.monotonic() >= end:
                raise
            time.sleep(0.1)


class OwnedChrome:
    def __init__(self, driver: Any, directory: tempfile.TemporaryDirectory,
                 profile: Path, driver_copy: Path):
        self._driver = driver
        self._directory = directory
        self._profile = profile
        self._copy = driver_copy
        self._closed = False

    def __getattr__(self, name: str) -> Any:
        return getattr(self._driver, name)

    def quit(self) -> None:
        if self._closed:
            return
        self._closed = True
        captured = _owned_processes(self._profile, self._copy)
        try:
            self._driver.quit()
        finally:
            _cleanup(self._directory, self._profile, self._copy, captured)


class UndetectedChromeFactory:
    def __init__(self, chrome: Path, chromedriver: Path, command_timeout: int = 30):
        self.chrome = chrome
        self.chromedriver = chromedriver
        self.command_timeout = command_timeout
        self.capture_console = False

    def start(self, mode: BrowserMode) -> OwnedChrome:
        if not Path("/proc").is_dir():
            raise BotRunError("UC_REQUIRES_LINUX", "browser")
        if not self.chrome.is_file() or not self.chromedriver.is_file():
            raise BotRunError("UC_EXECUTABLE_UNAVAILABLE", "browser")
        try:
            import undetected_chromedriver as uc  # type: ignore[import-not-found]
        except ImportError as error:
            raise BotRunError("UC_DEPENDENCY_UNAVAILABLE", "browser") from error
        directory = tempfile.TemporaryDirectory(prefix="bot-uc-")
        profile = Path(directory.name) / "profile"
        driver_copy = Path(directory.name) / "chromedriver"
        driver = None
        try:
            shutil.copy2(self.chromedriver, driver_copy)
            version = subprocess.run([str(driver_copy), "--version"], check=True,
                capture_output=True, text=True, timeout=5).stdout.split()[1]
            options = uc.ChromeOptions()
            options.add_argument("--window-size=1360,900")
            prefs = {"performance": "ALL"}
            if self.capture_console:
                prefs["browser"] = "ALL"
            options.set_capability("goog:loggingPrefs", prefs)
            driver = uc.Chrome(options=options, driver_executable_path=str(driver_copy),
                browser_executable_path=str(self.chrome), user_data_dir=str(profile),
                version_main=int(version.split(".")[0]), headless=mode == BrowserMode.HEADLESS,
                no_sandbox=False, use_subprocess=True)
            owned = OwnedChrome(driver, directory, profile, driver_copy)
            driver.command_executor._client_config.timeout = self.command_timeout
            driver.set_page_load_timeout(self.command_timeout)
            driver.set_script_timeout(self.command_timeout)
            return owned
        except Exception:
            try:
                if driver is not None:
                    driver.quit()
            finally:
                _cleanup(directory, profile, driver_copy)
            raise
