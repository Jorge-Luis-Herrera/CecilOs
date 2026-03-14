"""
Cecil-Brain Rolling Validator  (Phase 4)

Periodically re-validates cached skills so that stale plans are detected
and evicted before they can cause execution failures at runtime.

Design principles
─────────────────
• Non-blocking  — runs on a daemon thread; never pauses the GUI.
• Rate-limited  — validates at most N skills per cycle to avoid thrashing.
• Conservative  — only evicts a skill after K consecutive probe failures, not
                  after a single transient error.
• Transparent   — emits structured ValidationEvent objects consumed by the
                  GUI log; the validator itself has no UI dependency.
• Testable      — all validation logic is pure (no subprocess / AT-SPI side
                  effects in the core).  Probes are injected as callables.

Lifecycle
─────────
    v = RollingValidator(cache, probe_fn=..., interval_s=3600, batch=10)
    v.start()           # launches daemon thread
    v.request_immediate("skill-id")  # optional: force-validate one skill now
    v.stop()            # graceful shutdown (waits for current batch to finish)

ValidationEvent
───────────────
    emitted via an optional on_event callback:
    on_event(ValidationEvent(skill_id, result, reason))
    result ∈ {"ok", "degraded", "invalid", "skipped"}
"""

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable, List, Optional

from .skill_cache import CachedSkill, SkillCache

logger = logging.getLogger("cecil.brain.validator")

# ── Constants ──────────────────────────────────────────────────────────────────

DEFAULT_INTERVAL_S   = 3_600          # 1 hour between full validation sweeps
DEFAULT_BATCH_SIZE   = 10             # skills validated per cycle
STALE_DAYS           = 30            # skills not validated in N days → priority
MIN_SUCCESS_RATE     = 0.25           # below this → immediate eviction candidate
FAILURE_STRIKES      = 3             # consecutive probe failures before eviction
DEGRADED_RATE        = 0.50          # success_rate below this → "degraded"

# ── Data structures ────────────────────────────────────────────────────────────

@dataclass
class ValidationEvent:
    """Result of validating a single skill."""
    skill_id:  str
    result:    str                    # "ok" | "degraded" | "invalid" | "skipped"
    reason:    str = ""
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class ValidationStats:
    """Aggregate stats for the current validator session."""
    cycles_completed: int = 0
    skills_checked:   int = 0
    skills_ok:        int = 0
    skills_degraded:  int = 0
    skills_evicted:   int = 0
    last_cycle_at:    Optional[str] = None


# ── Probe helpers ──────────────────────────────────────────────────────────────

def _default_probe(skill: CachedSkill) -> bool:
    """
    Default lightweight probe: re-checks if the skill's *steps* are still
    structurally consistent (non-empty, known intents, required fields present).

    This is a heuristic probe — it does NOT execute the skill against the live
    desktop.  A full live probe requires injecting an executor callable.

    Returns True if skill looks healthy, False otherwise.
    """
    if not skill.steps:
        return False

    KNOWN_INTENTS = {
        "click_button", "type_text", "key_press", "launch_app",
        "open_terminal", "run_command", "navigate", "close_app",
        "scroll", "wait", "screenshot", "unknown",
    }

    for step in skill.steps:
        intent = getattr(step, "intent", None)
        if not intent:
            return False
        # Allow unknown intents: graceful degradation, not hard failure
        if intent not in KNOWN_INTENTS:
            logger.debug(f"Unknown intent '{intent}' in skill {skill.id}")

    return True


# ── Selector ───────────────────────────────────────────────────────────────────

def _select_batch(
    skills: List[CachedSkill],
    batch_size: int,
    stale_days: int,
) -> List[CachedSkill]:
    """
    Priority-order skills for validation in this cycle.

    Priority (highest first):
    1. Never validated
    2. Not validated in > stale_days
    3. Low success_rate (most likely broken)
    4. Least-recently validated
    """
    now = datetime.utcnow()
    stale_cutoff = now - timedelta(days=stale_days)

    def _priority(s: CachedSkill) -> tuple:
        # Lower tuple value → higher priority (sort ascending)
        never = s.last_validated is None
        stale = (
            False if s.last_validated is None
            else datetime.fromisoformat(s.last_validated) < stale_cutoff
        )
        rate = s.success_rate
        last_dt = (
            datetime.min if s.last_validated is None
            else datetime.fromisoformat(s.last_validated)
        )
        # (never, stale, -rate, last_validated_asc)
        return (not never, not stale, rate, last_dt)

    sorted_skills = sorted(skills, key=_priority)
    return sorted_skills[:batch_size]


# ── Core validator ─────────────────────────────────────────────────────────────

class RollingValidator:
    """
    Background daemon that periodically re-validates cached skills.

    Parameters
    ──────────
    cache       : SkillCache to operate on.
    probe_fn    : callable(CachedSkill) → bool  — health probe.
                  Defaults to _default_probe (structural check).
                  Inject a live-execution probe for full validation.
    interval_s  : seconds between full validation cycles (default 3600).
    batch_size  : max skills per cycle (default 10).
    stale_days  : skills not validated in this many days get priority.
    on_event    : optional callback(ValidationEvent) for UI/logging.
    """

    def __init__(
        self,
        cache: SkillCache,
        probe_fn: Optional[Callable[[CachedSkill], bool]] = None,
        interval_s: int = DEFAULT_INTERVAL_S,
        batch_size: int = DEFAULT_BATCH_SIZE,
        stale_days: int = STALE_DAYS,
        on_event: Optional[Callable[[ValidationEvent], None]] = None,
    ):
        self._cache      = cache
        self._probe      = probe_fn or _default_probe
        self._interval_s = interval_s
        self._batch_size = batch_size
        self._stale_days = stale_days
        self._on_event   = on_event

        self._stop_event     = threading.Event()
        self._immediate_ids: List[str] = []
        self._lock           = threading.Lock()
        self._thread: Optional[threading.Thread] = None

        # Consecutive failure counters per skill_id
        self._strike_counts: dict = {}

        self.stats = ValidationStats()
        self.running = False

    # ── Public API ─────────────────────────────────────────

    def start(self) -> None:
        """Start the background validation thread."""
        if self.running:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="CecilValidator"
        )
        self._thread.start()
        self.running = True
        logger.info(
            f"RollingValidator started (interval={self._interval_s}s, "
            f"batch={self._batch_size}, stale={self._stale_days}d)"
        )

    def stop(self, timeout: float = 5.0) -> None:
        """Signal the validation loop to stop and wait for it."""
        if not self.running:
            return
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=timeout)
        self.running = False
        logger.info("RollingValidator stopped")

    def request_immediate(self, skill_id: str) -> None:
        """
        Request that a specific skill be validated on the next cycle,
        regardless of its normal schedule.
        """
        with self._lock:
            if skill_id not in self._immediate_ids:
                self._immediate_ids.append(skill_id)
        logger.debug(f"Immediate validation queued: {skill_id}")

    # ── Internal loop ──────────────────────────────────────

    def _loop(self) -> None:
        """Main validation loop — sleeps between cycles."""
        logger.info("Validator loop running")
        # First cycle: short delay so startup isn't blocked
        self._stop_event.wait(timeout=10.0)

        while not self._stop_event.is_set():
            try:
                self._run_cycle()
            except Exception as e:
                logger.error(f"Validator cycle error: {e}", exc_info=True)

            # Sleep interval in small chunks to remain responsive to stop()
            deadline = time.monotonic() + self._interval_s
            while time.monotonic() < deadline and not self._stop_event.is_set():
                self._stop_event.wait(timeout=min(30.0, deadline - time.monotonic()))

        logger.info("Validator loop exited")

    def _run_cycle(self) -> None:
        """Execute one validation cycle."""
        all_skills = self._cache.list_skills()
        if not all_skills:
            logger.debug("No skills in cache — skipping cycle")
            return

        # Prioritise explicitly requested IDs first
        with self._lock:
            immediate = list(self._immediate_ids)
            self._immediate_ids.clear()

        forced = [s for s in all_skills if s.id in immediate]
        remaining = [s for s in all_skills if s.id not in immediate]
        scheduled = _select_batch(remaining, max(0, self._batch_size - len(forced)), self._stale_days)

        batch = forced + scheduled
        logger.info(f"Validation cycle: {len(batch)} skills (forced={len(forced)}, scheduled={len(scheduled)})")

        checked = ok = degraded = evicted = 0

        for skill in batch:
            if self._stop_event.is_set():
                break
            event = self._validate_one(skill)
            checked += 1

            if event.result == "ok":
                ok += 1
            elif event.result == "degraded":
                degraded += 1
            elif event.result == "invalid":
                evicted += 1

            if self._on_event:
                try:
                    self._on_event(event)
                except Exception as cb_err:
                    logger.warning(f"on_event callback error: {cb_err}")

        # Update aggregate stats
        self.stats.cycles_completed += 1
        self.stats.skills_checked   += checked
        self.stats.skills_ok        += ok
        self.stats.skills_degraded  += degraded
        self.stats.skills_evicted   += evicted
        self.stats.last_cycle_at     = datetime.utcnow().isoformat()

        logger.info(
            f"Cycle done — checked={checked} ok={ok} degraded={degraded} evicted={evicted}"
        )

    def _validate_one(self, skill: CachedSkill) -> ValidationEvent:
        """
        Validate a single skill.

        Algorithm:
        1. Cheap filters first (skip clearly broken stats).
        2. Run probe function.
        3. Record result; apply strike logic for eviction.
        4. Update last_validated timestamp in cache.
        """
        sid = skill.id

        # ── 1. Quick-reject: permanently bad success_rate ──
        total = skill.success_count + skill.failure_count
        if total >= 5 and skill.success_rate < MIN_SUCCESS_RATE:
            # Evict without running probe — it's already demonstrably broken
            self._evict(skill, reason=f"success_rate={skill.success_rate:.0%} < {MIN_SUCCESS_RATE:.0%}")
            return ValidationEvent(sid, "invalid", reason="low_success_rate")

        # ── 2. Run probe ───────────────────────────────────
        try:
            healthy = self._probe(skill)
        except Exception as probe_err:
            logger.warning(f"Probe raised exception for {sid}: {probe_err}")
            healthy = False

        # ── 3. Update last_validated ───────────────────────
        self._touch_validated(skill)

        # ── 4. Strike logic ────────────────────────────────
        if healthy:
            # Reset strike counter on success
            self._strike_counts.pop(sid, None)
            rate = skill.success_rate
            if total > 0 and rate < DEGRADED_RATE:
                logger.info(f"Skill {sid} degraded (rate={rate:.0%})")
                return ValidationEvent(sid, "degraded", reason=f"rate={rate:.0%}")
            logger.debug(f"Skill {sid} ok")
            return ValidationEvent(sid, "ok")
        else:
            strikes = self._strike_counts.get(sid, 0) + 1
            self._strike_counts[sid] = strikes
            if strikes >= FAILURE_STRIKES:
                self._evict(skill, reason=f"probe_failed ({strikes} strikes)")
                return ValidationEvent(sid, "invalid", reason=f"probe_failed_x{strikes}")
            else:
                logger.info(f"Skill {sid} probe failed (strike {strikes}/{FAILURE_STRIKES})")
                return ValidationEvent(sid, "degraded", reason=f"probe_strike_{strikes}")

    # ── Cache helpers ──────────────────────────────────────

    def _evict(self, skill: CachedSkill, reason: str) -> None:
        """Invalidate skill in cache and log eviction."""
        logger.warning(f"Evicting skill {skill.id} ({skill.command!r}): {reason}")
        self._cache.invalidate(skill.id)
        self._strike_counts.pop(skill.id, None)

    def _touch_validated(self, skill: CachedSkill) -> None:
        """Update last_validated timestamp in the cache."""
        try:
            skill.last_validated = datetime.utcnow().isoformat()
            self._cache.save(skill)
        except Exception as e:
            logger.warning(f"Could not touch last_validated for {skill.id}: {e}")


# ── Module-level convenience factory ──────────────────────────────────────────

def make_validator(
    cache: SkillCache,
    *,
    probe_fn: Optional[Callable[[CachedSkill], bool]] = None,
    interval_s: int = DEFAULT_INTERVAL_S,
    batch_size: int = DEFAULT_BATCH_SIZE,
    on_event: Optional[Callable[[ValidationEvent], None]] = None,
) -> RollingValidator:
    """Create and start a RollingValidator with sensible defaults."""
    v = RollingValidator(
        cache=cache,
        probe_fn=probe_fn,
        interval_s=interval_s,
        batch_size=batch_size,
        on_event=on_event,
    )
    v.start()
    return v
