from selenium.webdriver.common.by import By

from app.domain.contracts import BotContext, BotDescriptor, BotResult, BotRunError, RunStatus


class ExampleBot:
    descriptor = BotDescriptor(
        bot_id="local-smoke", name="Local Browser Smoke Test",
        description="Visits an inline HTML document to prove remote browser wiring without a service.")

    def run(self, ctx: BotContext) -> BotResult:
        ctx.check_deadline()
        ctx.driver.get("data:text/html,<title>Local Smoke</title><main id='ready'>ready</main>")
        if ctx.driver.find_element(By.ID, "ready").text != "ready":
            raise BotRunError("LOCAL_ASSERTION_FAILED", "verification")
        return BotResult(RunStatus.SUCCEEDED, evidence="observed_local_ready_text")
