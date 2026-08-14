from types import SimpleNamespace

import app.manager as manager_module
from app.manager import BotManager


def _state(name: str, short: str):
    return SimpleNamespace(
        name=name,
        short=short,
        acc={"cookies": {"crypted_hhuid": "same-hh-user"}},
        llm_enabled=True,
        paused=False,
        _deleted=False,
    )


def _manager(*states):
    manager = object.__new__(BotManager)
    manager.account_states = []
    manager.temp_states = {idx: state for idx, state in enumerate(states)}
    return manager


def test_application_profile_owns_shared_account_chat(monkeypatch):
    fullstack = _state("Никита — Fullstack", "Fullstack")
    frontend = _state("Никита — Frontend", "Frontend")
    manager = _manager(fullstack, frontend)
    monkeypatch.setattr(
        manager_module,
        "get_applied_accounts",
        lambda vacancy_id: {"Никита — Frontend"},
    )

    assert manager._llm_profile_owner(frontend, "123") == (True, "Frontend")
    assert manager._llm_profile_owner(fullstack, "123") == (False, "Frontend")


def test_unknown_vacancy_has_one_deterministic_owner(monkeypatch):
    fullstack = _state("Никита — Fullstack", "Fullstack")
    frontend = _state("Никита — Frontend", "Frontend")
    manager = _manager(fullstack, frontend)
    monkeypatch.setattr(manager_module, "get_applied_accounts", lambda vacancy_id: set())

    assert manager._llm_profile_owner(fullstack, "") == (True, "Fullstack")
    assert manager._llm_profile_owner(frontend, "") == (False, "Fullstack")
