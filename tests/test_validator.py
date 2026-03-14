"""
Phase 4 Test Suite — Rolling Validator

Tests cover:
  1. Batch selector priority logic (never-validated → stale → low-rate → recent)
  2. _validate_one: healthy skill → ok
  3. _validate_one: degraded rate → degraded event
  4. _validate_one: failing probe → strike accumulation → eviction
  5. _validate_one: low success_rate fast-path eviction
  6. _run_cycle: events emitted + stats updated
  7. request_immediate: forced skill promoted to front of batch
  8. Validator start/stop lifecycle
  9. Integration: make_validator factory
"""

import sys
import os
import time
import threading
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from datetime import datetime, timedelta
from typing import List

from cecil_brain.skill_cache import SkillCache, CachedSkill, SemanticStep
from cecil_brain.validator import (
    RollingValidator, ValidationEvent, ValidationStats,
    _select_batch, _default_probe, make_validator,
    STALE_DAYS, FAILURE_STRIKES, MIN_SUCCESS_RATE, DEGRADED_RATE,
)

# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _make_skill(
    id_: str,
    command: str = "test command",
    success: int = 5,
    failure: int = 0,
    last_validated: str | None = None,
    steps: list | None = None,
) -> CachedSkill:
    return CachedSkill(
        id=id_,
        command=command,
        command_embedding=[],
        steps=steps if steps is not None else [SemanticStep(intent="click_button", target="OK")],
        success_count=success,
        failure_count=failure,
        last_validated=last_validated,
    )


def _make_cache() -> SkillCache:
    """Create a fresh in-memory-like SkillCache using a temp directory."""
    tmp = tempfile.mkdtemp(prefix="cecil_test_")
    return SkillCache(cache_dir=tmp)


def _banner(title: str):
    print(f"\n{'='*60}")
    print(f"TEST: {title}")
    print('='*60)


# ─────────────────────────────────────────────
# TEST 1: Batch selector priority
# ─────────────────────────────────────────────

def test_batch_selector_priority():
    _banner("Batch selector — ordering by priority")

    now = datetime.utcnow()

    # never validated
    s_never  = _make_skill("never",  last_validated=None)
    # stale (> STALE_DAYS ago)
    stale_dt = (now - timedelta(days=STALE_DAYS + 5)).isoformat()
    s_stale  = _make_skill("stale",  last_validated=stale_dt, success=4, failure=1)
    # low rate (validated recently)
    recent_dt = (now - timedelta(hours=1)).isoformat()
    s_low    = _make_skill("low",    last_validated=recent_dt, success=1, failure=9)
    # healthy (validated recently, high rate)
    s_good   = _make_skill("good",   last_validated=recent_dt, success=10, failure=0)

    skills = [s_good, s_low, s_stale, s_never]
    batch = _select_batch(skills, batch_size=4, stale_days=STALE_DAYS)

    ids = [s.id for s in batch]
    print(f"  Order: {ids}")

    assert ids[0] == "never",  f"Expected 'never' first, got {ids[0]}"
    assert ids[1] == "stale",  f"Expected 'stale' second, got {ids[1]}"
    # low-rate and good are both recent; low-rate should come before good
    assert "low" in ids and "good" in ids
    assert ids.index("low") < ids.index("good"), "low-rate should precede high-rate"
    print("  ✓ priority order correct")


# ─────────────────────────────────────────────
# TEST 2: validate_one — healthy skill → ok
# ─────────────────────────────────────────────

def test_validate_healthy():
    _banner("validate_one — healthy skill → ok")

    cache = _make_cache()
    skill = _make_skill("h1", success=10, failure=1)
    cache.save(skill)

    v = RollingValidator(cache, probe_fn=lambda s: True)
    event = v._validate_one(skill)

    print(f"  result={event.result!r}  reason={event.reason!r}")
    assert event.result == "ok", f"Expected ok, got {event.result}"
    print("  ✓ healthy → ok")


# ─────────────────────────────────────────────
# TEST 3: validate_one — degraded rate → degraded
# ─────────────────────────────────────────────

def test_validate_degraded_rate():
    _banner("validate_one — degraded rate → degraded")

    cache = _make_cache()
    # 30% success rate → below DEGRADED_RATE (0.50)
    skill = _make_skill("d1", success=3, failure=7)
    cache.save(skill)

    v = RollingValidator(cache, probe_fn=lambda s: True)
    event = v._validate_one(skill)

    print(f"  success_rate={skill.success_rate:.0%}  result={event.result!r}")
    assert event.result == "degraded", f"Expected degraded, got {event.result}"
    print("  ✓ low-rate skill flagged as degraded")


# ─────────────────────────────────────────────
# TEST 4: validate_one — probe fails → strikes → eviction
# ─────────────────────────────────────────────

def test_validate_strikes_to_eviction():
    _banner("validate_one — probe failures → strike accumulation → eviction")

    cache = _make_cache()
    skill = _make_skill("s1", success=10, failure=0)
    cache.save(skill)

    v = RollingValidator(cache, probe_fn=lambda s: False)

    results = []
    for i in range(FAILURE_STRIKES):
        # Re-fetch skill each time so counts are current
        skills = cache.list_skills()
        s = next((x for x in skills if x.id == "s1"), skill)
        event = v._validate_one(s)
        results.append(event.result)
        print(f"  Strike {i+1}: result={event.result!r}")

    # First (FAILURE_STRIKES-1) should be degraded, last should be invalid
    assert results[-1] == "invalid", f"Expected invalid on final strike, got {results[-1]}"
    assert all(r == "degraded" for r in results[:-1]), \
        f"Expected degraded before eviction, got {results[:-1]}"
    print(f"  ✓ eviction after {FAILURE_STRIKES} consecutive probe failures")


# ─────────────────────────────────────────────
# TEST 5: validate_one — low success_rate fast-path
# ─────────────────────────────────────────────

def test_validate_fastpath_eviction():
    _banner("validate_one — low success_rate fast-path eviction")

    cache = _make_cache()
    # < MIN_SUCCESS_RATE and >= 5 executions
    skill = _make_skill("e1", success=1, failure=20)
    cache.save(skill)

    probe_called = []
    def probe(s):
        probe_called.append(True)
        return True  # Would say healthy, but fast-path should skip it

    v = RollingValidator(cache, probe_fn=probe)
    event = v._validate_one(skill)

    print(f"  result={event.result!r}  probe_called={bool(probe_called)}")
    assert event.result == "invalid", f"Expected invalid, got {event.result}"
    assert not probe_called, "Probe should NOT be called in fast-path eviction"
    print("  ✓ fast-path eviction without probe")


# ─────────────────────────────────────────────
# TEST 6: _run_cycle — stats updated + events emitted
# ─────────────────────────────────────────────

def test_run_cycle_stats():
    _banner("_run_cycle — stats updated and events emitted")

    cache = _make_cache()

    # 3 healthy skills + 1 degraded (< 5 executions so fast-path skipped, rate 25% < DEGRADED_RATE)
    for i in range(3):
        cache.save(_make_skill(f"ok{i}", success=10, failure=0))
    cache.save(_make_skill("deg", success=1, failure=3))  # total=4 → fast-path skipped; rate=25% < 50%

    events: List[ValidationEvent] = []
    v = RollingValidator(cache, probe_fn=lambda s: True, on_event=events.append)
    v._run_cycle()

    print(f"  stats: {v.stats}")
    print(f"  events: {[(e.result, e.skill_id[:6]) for e in events]}")

    assert v.stats.cycles_completed == 1
    assert v.stats.skills_checked == 4
    # The degraded one should emit an event
    degraded_events = [e for e in events if e.result == "degraded"]
    assert len(degraded_events) >= 1, "Expected at least 1 degraded event"
    print("  ✓ cycle stats and events correct")


# ─────────────────────────────────────────────
# TEST 7: request_immediate — forced to front
# ─────────────────────────────────────────────

def test_request_immediate():
    _banner("request_immediate — forced skill validated first in cycle")

    cache = _make_cache()

    # 5 recently-validated, healthy skills
    recent_dt = datetime.utcnow().isoformat()
    for i in range(5):
        cache.save(_make_skill(f"r{i}", success=10, failure=0, last_validated=recent_dt))

    # 1 skill that has never been validated — would normally be first
    cache.save(_make_skill("never", success=5, failure=0, last_validated=None))

    # Force the recently-validated "r3" to be checked immediately
    validated_ids: List[str] = []
    def probe(s):
        validated_ids.append(s.id)
        return True

    v = RollingValidator(cache, probe_fn=probe, batch_size=3)
    v.request_immediate("r3")
    v._run_cycle()

    print(f"  Validated IDs: {validated_ids}")
    assert "r3" in validated_ids, "Immediate-requested skill must be in batch"
    assert validated_ids[0] == "r3", "Immediate-requested skill must be first in batch"
    print("  ✓ immediate request promoted to front")


# ─────────────────────────────────────────────
# TEST 8: start/stop lifecycle
# ─────────────────────────────────────────────

def test_lifecycle():
    _banner("Validator start/stop lifecycle")

    cache = _make_cache()
    v = RollingValidator(cache, interval_s=9999, batch_size=1)

    assert not v.running, "Should not be running before start()"
    v.start()
    assert v.running, "Should be running after start()"

    # Double start should be a no-op
    v.start()
    assert v.running

    v.stop(timeout=2.0)
    assert not v.running, "Should not be running after stop()"
    print("  ✓ start/stop lifecycle correct")


# ─────────────────────────────────────────────
# TEST 9: make_validator factory + default_probe
# ─────────────────────────────────────────────

def test_make_validator_and_default_probe():
    _banner("make_validator factory + _default_probe structural check")

    cache = _make_cache()

    # Good skill
    good = _make_skill("g1", steps=[SemanticStep(intent="click_button", target="OK")])
    assert _default_probe(good) is True, "Good skill should pass default probe"

    # Empty steps
    empty = _make_skill("e1", steps=[])
    assert _default_probe(empty) is False, "Empty steps should fail default probe"

    # No intent field
    bad_step = SemanticStep(intent="", target="X")
    bad = _make_skill("b1", steps=[bad_step])
    assert _default_probe(bad) is False, "Missing intent should fail default probe"

    # make_validator creates and starts a validator
    v = make_validator(cache, interval_s=9999)
    assert v.running, "make_validator should start the validator"
    v.stop(timeout=2.0)
    print("  ✓ default probe + factory correct")


# ─────────────────────────────────────────────
# Runner
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("\n🔁 CecilOs Phase 4 Test Suite")
    print("Rolling Validator — Background Skill Validation\n")

    tests = [
        test_batch_selector_priority,
        test_validate_healthy,
        test_validate_degraded_rate,
        test_validate_strikes_to_eviction,
        test_validate_fastpath_eviction,
        test_run_cycle_stats,
        test_request_immediate,
        test_lifecycle,
        test_make_validator_and_default_probe,
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
    print(f"{'✓ Todos los tests de Fase 4 completados' if failed == 0 else f'✗ {failed} tests fallaron'}")
    print(f"{'='*60}\n")
    sys.exit(0 if failed == 0 else 1)
