"""
Phase 7 — Self-correction tests
================================
Run with:  python -m pytest test_self_correction.py -v
"""

import pytest
from cecil_brain.self_correction import (
    CorrectionResult,
    RetryStrategy,
    SelfCorrector,
    TERMINAL_FALLBACKS,
    APP_ALIASES,
    suggest_layer_escalation,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def corrector():
    return SelfCorrector()


# ── 1. open_terminal: cycles through TERMINAL_FALLBACKS ──────────────────────

def test_open_terminal_first_failure_tries_next(corrector):
    """Attempt 0 with kitty failing → TRY_ALTERNATIVE with gnome-terminal."""
    result = corrector.suggest("open_terminal", {"app": "kitty"}, attempt=0, error="launch_failed")
    assert result.strategy == RetryStrategy.TRY_ALTERNATIVE
    assert result.alternative_args.get("app") == "gnome-terminal"


def test_open_terminal_second_failure_advances(corrector):
    """Attempt 0 with gnome-terminal → xterm."""
    result = corrector.suggest("open_terminal", {"app": "gnome-terminal"}, attempt=0)
    assert result.strategy == RetryStrategy.TRY_ALTERNATIVE
    assert result.alternative_args.get("app") == "xterm"


def test_open_terminal_exhausted_escalates_l2(corrector):
    """Last terminal in fallback list → ESCALATE_L2."""
    last = TERMINAL_FALLBACKS[-1]
    result = corrector.suggest("open_terminal", {"app": last}, attempt=0)
    assert result.strategy == RetryStrategy.ESCALATE_L2


# ── 2. open_app: tries aliases ────────────────────────────────────────────────

def test_open_app_known_alias(corrector):
    """firefox failing → firefox-esr (first alias)."""
    result = corrector.suggest("open_app", {"app": "firefox"}, attempt=0, error="not_found")
    assert result.strategy == RetryStrategy.TRY_ALTERNATIVE
    assert result.alternative_args["app"] == APP_ALIASES["firefox"][0]


def test_open_app_second_alias(corrector):
    """firefox failing on second attempt → second alias."""
    result = corrector.suggest("open_app", {"app": "firefox"}, attempt=1, error="not_found")
    assert result.strategy == RetryStrategy.TRY_ALTERNATIVE
    assert result.alternative_args["app"] == APP_ALIASES["firefox"][1]


def test_open_app_unknown_app_escalates_l2(corrector):
    """Unknown app with no aliases → ESCALATE_L2."""
    result = corrector.suggest("open_app", {"app": "totally_unknown_app_xyz"}, attempt=0)
    assert result.strategy == RetryStrategy.ESCALATE_L2


# ── 3. run_command / compile: retry once then escalate ───────────────────────

def test_run_command_first_failure_retries(corrector):
    result = corrector.suggest("run_command", {"cmd": "ls"}, attempt=0, error="type_failed")
    assert result.strategy == RetryStrategy.RETRY_SAME


def test_run_command_second_failure_escalates(corrector):
    result = corrector.suggest("run_command", {"cmd": "ls"}, attempt=1, error="type_failed")
    assert result.strategy == RetryStrategy.ESCALATE_L2


def test_compile_first_failure_retries(corrector):
    result = corrector.suggest("compile", {"cmd": "gcc main.c"}, attempt=0, error="type_failed")
    assert result.strategy == RetryStrategy.RETRY_SAME


# ── 4. type_text: retry once then escalate to L3 ─────────────────────────────

def test_type_text_first_failure_retries(corrector):
    result = corrector.suggest("type_text", {"text": "hola"}, attempt=0, error="type_failed")
    assert result.strategy == RetryStrategy.RETRY_SAME


def test_type_text_second_failure_escalates_l3(corrector):
    result = corrector.suggest("type_text", {"text": "hola"}, attempt=1, error="type_failed")
    assert result.strategy == RetryStrategy.ESCALATE_L3


# ── 5. create_file / navigate: escalate to L2 ────────────────────────────────

def test_create_file_escalates_l2(corrector):
    result = corrector.suggest("create_file", {"filename": "x.txt", "content": "hi"}, attempt=0)
    assert result.strategy == RetryStrategy.ESCALATE_L2


def test_navigate_escalates_l2(corrector):
    result = corrector.suggest("navigate", {"target": "https://example.com"}, attempt=0)
    assert result.strategy == RetryStrategy.ESCALATE_L2


# ── 6. Max-attempts hard cap ──────────────────────────────────────────────────

def test_max_attempts_aborts(corrector):
    """Reaching MAX_ATTEMPTS - 1 always returns ABORT regardless of task type."""
    result = corrector.suggest("open_terminal", {"app": "kitty"}, attempt=SelfCorrector.MAX_ATTEMPTS - 1)
    assert result.strategy == RetryStrategy.ABORT
    assert result.is_terminal


# ── 7. suggest_layer_escalation ──────────────────────────────────────────────

def test_layer1_failure_escalates_to_l2():
    result = suggest_layer_escalation(current_layer=1, attempt=0, error="intent_failed")
    assert result.strategy == RetryStrategy.ESCALATE_L2
    assert not result.is_terminal


def test_layer2_failure_escalates_to_l3():
    result = suggest_layer_escalation(current_layer=2, attempt=0, error="plan_failed")
    assert result.strategy == RetryStrategy.ESCALATE_L3


def test_layer3_failure_aborts():
    result = suggest_layer_escalation(current_layer=3, attempt=0, error="vision_failed")
    assert result.strategy == RetryStrategy.ABORT


def test_layer_escalation_max_attempts_aborts():
    result = suggest_layer_escalation(current_layer=1, attempt=1, max_attempts=2)
    assert result.strategy == RetryStrategy.ABORT


# ── 8. CorrectionResult helpers ──────────────────────────────────────────────

def test_correction_result_is_terminal():
    r = CorrectionResult(strategy=RetryStrategy.ABORT, reason="test")
    assert r.is_terminal
    r2 = CorrectionResult(strategy=RetryStrategy.RETRY_SAME, reason="test")
    assert not r2.is_terminal


def test_correction_result_needs_escalation():
    for s in (RetryStrategy.ESCALATE_L2, RetryStrategy.ESCALATE_L3):
        r = CorrectionResult(strategy=s, reason="test")
        assert r.needs_escalation
    for s in (RetryStrategy.RETRY_SAME, RetryStrategy.TRY_ALTERNATIVE, RetryStrategy.ABORT):
        r = CorrectionResult(strategy=s, reason="test")
        assert not r.needs_escalation


# ── 9. Helper methods: next_terminal / next_app / alternatives_for ────────────

def test_next_terminal(corrector):
    assert corrector.next_terminal("kitty") == "gnome-terminal"
    assert corrector.next_terminal(TERMINAL_FALLBACKS[-1]) is None


def test_next_app_known(corrector):
    first_alias = APP_ALIASES["firefox"][0]
    assert corrector.next_app("firefox") == first_alias


def test_next_app_unknown(corrector):
    assert corrector.next_app("nonexistent_app_xyz") is None


def test_alternatives_for(corrector):
    alts = corrector.alternatives_for("chrome")
    assert len(alts) > 0
    assert all(isinstance(a, str) for a in alts)
