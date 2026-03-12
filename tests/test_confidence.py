"""
Phase 6 Test Suite — Confidence Scorer

Tests cover:
  1.  Safe command (open app) → score ≥ threshold, no confirm
  2.  Destructive command (delete) → needs_confirm=True, is_destructive=True
  3.  High-risk command (close app) → needs_confirm=True
  4.  Medium-risk command (install) → score reduced
  5.  No-cache path: semantic_sim/success_rate clamped to 1.0
  6.  Cache hit with low similarity → low score
  7.  Cache hit with high similarity + good rate → high score
  8.  Ambiguous command (no clear verb) → clarity penalty
  9.  HIGH_RISK_ALWAYS=True: destructive always confirms even at sim=1.0
  10. explain() returns non-empty string
  11. is_safe() convenience helper
  12. score clamped to [0, 1] for extreme inputs
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cecil_brain.confidence import (
    score_action, is_safe, explain,
    CONFIRM_THRESHOLD, HIGH_RISK_ALWAYS,
    RISK_HIGH, RISK_DESTRUCTIVE,
    W_SIM, W_RATE, W_RISK, W_CLAR,
)


def _banner(title: str):
    print(f"\n{'='*60}")
    print(f"TEST: {title}")
    print("=" * 60)


# ── TEST 1: Safe command ────────────────────────────────────

def test_safe_open():
    _banner("Safe command — open app → no confirmation needed")
    r = score_action("abre firefox", is_cache_hit=False)
    print(f"  score={r.score:.2f}  needs_confirm={r.needs_confirm}  explanation={r.explanation}")
    assert r.score >= CONFIRM_THRESHOLD, f"Expected score ≥ {CONFIRM_THRESHOLD}, got {r.score:.2f}"
    assert not r.needs_confirm
    assert not r.is_destructive
    print("  ✓")


# ── TEST 2: Destructive command ─────────────────────────────

def test_destructive_delete():
    _banner("Destructive command — 'borra el archivo' → confirm + destructive")
    r = score_action("borra el archivo main.rs", is_cache_hit=False)
    print(f"  score={r.score:.2f}  needs_confirm={r.needs_confirm}  is_destructive={r.is_destructive}")
    assert r.needs_confirm, "Destructive command must require confirmation"
    assert r.is_destructive, "Should be flagged as destructive"
    print("  ✓")


def test_destructive_rm():
    _banner("Destructive command — English 'rm build' → confirm + destructive")
    r = score_action("rm build", is_cache_hit=False)
    print(f"  score={r.score:.2f}  needs_confirm={r.needs_confirm}  is_destructive={r.is_destructive}")
    assert r.is_destructive
    assert r.needs_confirm
    print("  ✓")


# ── TEST 3: High-risk command ───────────────────────────────

def test_high_risk_close():
    _banner("High-risk command — task_type=close_app → confirm")
    r = score_action("cierra vscode", task_type="close_app", is_cache_hit=False)
    print(f"  score={r.score:.2f}  needs_confirm={r.needs_confirm}  risk_label={r.risk_label!r}")
    assert r.needs_confirm, "close_app should require confirmation"
    print("  ✓")


def test_high_risk_sudo():
    _banner("High-risk command — sudo → confirm")
    r = score_action("ejecuta sudo apt update", is_cache_hit=False)
    print(f"  score={r.score:.2f}  needs_confirm={r.needs_confirm}  risk_label={r.risk_label!r}")
    assert r.needs_confirm
    print("  ✓")


# ── TEST 4: Medium-risk command ─────────────────────────────

def test_medium_risk_install():
    _banner("Medium-risk command — install → score reduced but may not need confirm")
    r_install = score_action("instala python", is_cache_hit=False)
    r_safe    = score_action("abre firefox", is_cache_hit=False)
    print(f"  install score={r_install.score:.2f}  open score={r_safe.score:.2f}")
    assert r_install.score < r_safe.score, "Install should score lower than open"
    print("  ✓")


# ── TEST 5: No-cache path — sim and rate forced to 1.0 ──────

def test_no_cache_path():
    _banner("No-cache path — semantic_sim/success_rate clamped to 1.0")
    r_no_cache  = score_action("abre firefox", is_cache_hit=False,
                               semantic_sim=0.0, success_rate=0.0)
    r_with_vals = score_action("abre firefox", is_cache_hit=True,
                               semantic_sim=0.0, success_rate=0.0)
    print(f"  no_cache={r_no_cache.score:.2f}  with_low_cache={r_with_vals.score:.2f}")
    # No cache path should clamp to 1.0 → higher score than low-sim cache hit
    assert r_no_cache.score > r_with_vals.score, \
        "No-cache path should score higher than a low-similarity cache hit"
    print("  ✓")


# ── TEST 6: Low-similarity cache hit ───────────────────────

def test_low_sim_cache_hit():
    _banner("Low-similarity cache hit → low score → needs confirm")
    r = score_action("abre firefox", is_cache_hit=True,
                     semantic_sim=0.30, success_rate=0.50)
    print(f"  score={r.score:.2f}  needs_confirm={r.needs_confirm}")
    assert r.score < CONFIRM_THRESHOLD, f"Low-sim hit should score < {CONFIRM_THRESHOLD}"
    assert r.needs_confirm
    print("  ✓")


# ── TEST 7: High-similarity cache hit ──────────────────────

def test_high_sim_cache_hit():
    _banner("High-similarity + high success_rate → high score, no confirm")
    r = score_action("abre firefox", is_cache_hit=True,
                     semantic_sim=0.97, success_rate=0.95)
    print(f"  score={r.score:.2f}  needs_confirm={r.needs_confirm}")
    assert r.score >= CONFIRM_THRESHOLD, f"High-sim hit should score ≥ {CONFIRM_THRESHOLD}"
    assert not r.needs_confirm
    print("  ✓")


# ── TEST 8: Ambiguous command — no clear verb ───────────────

def test_ambiguous_command():
    _banner("Ambiguous command — no verb → clarity penalty")
    r_clear    = score_action("abre firefox", is_cache_hit=False)
    r_ambig    = score_action("firefox", is_cache_hit=False)
    print(f"  clear={r_clear.score:.2f}  ambiguous={r_ambig.score:.2f}")
    assert r_ambig.score < r_clear.score, "Ambiguous command should score lower"
    print("  ✓")


# ── TEST 9: HIGH_RISK_ALWAYS override ──────────────────────

def test_high_risk_always():
    _banner("HIGH_RISK_ALWAYS=True — destructive always confirms even at sim=1.0")
    if not HIGH_RISK_ALWAYS:
        print("  SKIP: HIGH_RISK_ALWAYS is False in config")
        return
    r = score_action("borra todo", is_cache_hit=True,
                     semantic_sim=1.0, success_rate=1.0)
    print(f"  score={r.score:.2f}  needs_confirm={r.needs_confirm}  is_destructive={r.is_destructive}")
    assert r.is_destructive
    assert r.needs_confirm, "Destructive must always confirm when HIGH_RISK_ALWAYS=True"
    print("  ✓")


# ── TEST 10: explain() non-empty ────────────────────────────

def test_explain():
    _banner("explain() returns non-empty string with score info")
    e = explain("abre firefox", is_cache_hit=False)
    print(f"  explanation: {e!r}")
    assert isinstance(e, str) and len(e) > 0
    assert "score=" in e
    print("  ✓")


# ── TEST 11: is_safe() helper ───────────────────────────────

def test_is_safe():
    _banner("is_safe() convenience helper")
    assert is_safe("abre firefox", is_cache_hit=False)       is True,  "open app should be safe"
    assert is_safe("borra el proyecto", is_cache_hit=False)  is False, "delete should not be safe"
    print("  ✓")


# ── TEST 12: Score clamping ─────────────────────────────────

def test_score_clamping():
    _banner("Score clamped to [0, 1] for extreme inputs")
    r_high = score_action("abre firefox", is_cache_hit=True,
                          semantic_sim=1.0, success_rate=1.0)
    r_low  = score_action("borra todo", is_cache_hit=True,
                          semantic_sim=0.0, success_rate=0.0)
    print(f"  high={r_high.score:.4f}  low={r_low.score:.4f}")
    assert 0.0 <= r_high.score <= 1.0
    assert 0.0 <= r_low.score  <= 1.0
    print("  ✓")


# ── Runner ──────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n📊 CecilOs Phase 6 Test Suite")
    print("Confidence Scorer + Confirmation Gate\n")

    tests = [
        test_safe_open,
        test_destructive_delete,
        test_destructive_rm,
        test_high_risk_close,
        test_high_risk_sudo,
        test_medium_risk_install,
        test_no_cache_path,
        test_low_sim_cache_hit,
        test_high_sim_cache_hit,
        test_ambiguous_command,
        test_high_risk_always,
        test_explain,
        test_is_safe,
        test_score_clamping,
    ]

    passed = failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as exc:
            print(f"  ✗ FAIL: {exc}")
            import traceback; traceback.print_exc()
            failed += 1

    print(f"\n{'='*60}")
    print(f"{'✓ Todos los tests de Fase 6 completados' if failed == 0 else f'✗ {failed}/{passed+failed} tests fallaron'}")
    print(f"{'='*60}\n")
    sys.exit(0 if failed == 0 else 1)
