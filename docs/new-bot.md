# Add a bot

1. Implement `Bot` (`descriptor` and `run(ctx)`) under `backend/app/bots/`.
2. Register its zero-argument factory in `build_registry` in
   `app/application/registry.py`. Duplicate IDs are rejected. No worker, ORM, API or
   frontend changes are needed; the UI loads descriptors from the API.
3. Use the injected `ctx.driver` and `ctx.check_deadline()` between blocking steps.
   Call `ctx.record_challenge(value)` immediately for legitimately observed challenge
   metadata; its independent commit may fail, in which case stop external work.
4. Call `ctx.report_manual_wait()` for a bounded Headful intervention. Return a terminal
   `BotResult` only after observing the site's actual outcome. Success needs nonempty
   evidence. Call `ctx.report_running()` when a reported human wait ends. Raise `BotRunError(code, stage, status)` for known failures; keep codes
   static and never include passwords, tokens or arbitrary page/exception strings.
5. Close bot-owned observers/resources in `finally`. The worker owns final browser quit.
   Never retry an external action whose outcome could already have succeeded.
6. Add deterministic tests, a real local browser fixture where appropriate, and
   explicitly opt-in live integration tests for external targets.

Minimal working Selenium implementation: `app/bots/examples/example_bot.py`.
It navigates to an inline HTML page and verifies the rendered `#ready` text. The
registry tests register a third independent example without changing execution/storage/UI.
The browser smoke test executes the actual included implementation when a driver is available.

To add another browser engine, implement a browser factory and matching page adapters.
The domain receives an injected driver; Selenium-specific bots still require Selenium APIs.
