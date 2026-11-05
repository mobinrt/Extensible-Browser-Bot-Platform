from dataclasses import asdict

import pytest

from app.domain.contracts import TERMINAL, BotResult, BrowserMode, RunStatus, transition_allowed


def test_queue_lifecycle_and_terminal_immutability():
    assert transition_allowed(RunStatus.QUEUED, RunStatus.RUNNING)
    assert transition_allowed(RunStatus.RUNNING, RunStatus.WAITING_FOR_HUMAN)
    assert transition_allowed(RunStatus.WAITING_FOR_HUMAN, RunStatus.RUNNING)
    for terminal in TERMINAL:
        assert transition_allowed(RunStatus.RUNNING, terminal)
        assert transition_allowed(RunStatus.WAITING_FOR_HUMAN, terminal)
        assert all(not transition_allowed(terminal, other) for other in RunStatus)
    assert not transition_allowed(RunStatus.QUEUED, RunStatus.SUCCEEDED)


def test_success_requires_observed_evidence():
    with pytest.raises(ValueError, match="Success requires"):
        BotResult(RunStatus.SUCCEEDED)
    with pytest.raises(ValueError, match="terminal"):
        BotResult(RunStatus.RUNNING)
    assert BotResult(RunStatus.SUCCEEDED, evidence="dom_verified").evidence == "dom_verified"
    assert BotResult(RunStatus.BLOCKED).status == RunStatus.BLOCKED


def test_serialization_of_results_and_modes():
    result = BotResult(RunStatus.SUCCEEDED, "marker", {"attempts": 1})
    assert asdict(result)["metadata"]["attempts"] == 1
    assert str(result.status) == "SUCCEEDED"
    assert BrowserMode("HEADFUL") == BrowserMode.HEADFUL
