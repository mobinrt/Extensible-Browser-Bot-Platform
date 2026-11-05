"""Smoke the running Compose stack, optionally checking persistence over restart.

Run from repository root: python3 scripts/acceptance.py --restart
No external CAPTCHA is included in this deterministic acceptance test.
"""
import argparse
import json
import subprocess
import time
from urllib.error import URLError
from urllib.request import Request, urlopen


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", default="http://127.0.0.1:8000/api/v1")
    parser.add_argument("--restart", action="store_true")
    args = parser.parse_args()

    def call(path, payload=None):
        request = Request(args.api + path, data=json.dumps(payload).encode() if payload else None,
                          headers={"Content-Type": "application/json"})
        with urlopen(request, timeout=10) as response:
            return json.load(response)

    def wait_ready():
        end = time.monotonic() + 90
        while time.monotonic() < end:
            try:
                if call("/health/ready")["status"] == "ready":
                    return
            except (URLError, TimeoutError):
                pass
            time.sleep(1)
        raise RuntimeError("API readiness timeout")

    wait_ready()
    assert {b["bot_id"] for b in call("/bots")} >= {"local-smoke", "arcaptcha-demo"}
    ids = []
    for mode in ["HEADLESS", "HEADFUL"]:
        run = call("/runs", {"bot_id": "local-smoke", "browser_mode": mode})
        ids.append(run["run_id"])
        end = time.monotonic() + 120
        while run["status"] in {"QUEUED", "RUNNING", "WAITING_FOR_HUMAN"}:
            if time.monotonic() >= end:
                raise RuntimeError(f"{mode} run did not finish")
            time.sleep(0.5)
            run = call("/runs/" + ids[-1])
        assert run["status"] == "SUCCEEDED", (mode, run["status"], run["error_code"])
        assert run["result_metadata"]["evidence"] == "observed_local_ready_text"
        print(mode, "SUCCEEDED", ids[-1])
    if args.restart:
        subprocess.run(["docker", "compose", "restart", "postgres", "api", "worker"], check=True)
        wait_ready()
        for run_id in ids:
            assert call("/runs/" + run_id)["status"] == "SUCCEEDED"
        print("History retained across service restart")


if __name__ == "__main__":
    main()
