from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.remote.client_config import ClientConfig
from urllib3.exceptions import HTTPError

from app.domain.contracts import BrowserMode


class SeleniumBrowserFactory:
    def __init__(self, url: str, command_timeout: int = 30):
        self.url = url
        self.command_timeout = command_timeout
        self.capture_console = False

    def start(self, mode: BrowserMode) -> webdriver.Remote:
        options = Options()
        options.add_argument("--window-size=1360,900")
        if mode == BrowserMode.HEADLESS:
            options.add_argument("--headless=new")
        logging_prefs = {"performance": "ALL"}
        if self.capture_console:
            logging_prefs["browser"] = "ALL"
        options.set_capability("goog:loggingPrefs", logging_prefs)
        driver = webdriver.Remote(command_executor=self.url, options=options,
                                  client_config=ClientConfig(remote_server_addr=self.url, timeout=self.command_timeout))
        try:
            driver.set_page_load_timeout(self.command_timeout)
            driver.set_script_timeout(self.command_timeout)
        except Exception:
            try:
                driver.quit()
            except (WebDriverException, HTTPError):
                pass
            raise
        return driver
