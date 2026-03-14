"""
Cecil-Brain Confidence Scorer  (Phase 6)

Assigns a composite confidence score to any pending action before it executes.
If the score falls below a threshold, the pipeline pauses and asks the user
to confirm or cancel.

Design goals
────────────
• Transparent  — every score comes with a human-readable explanation.
• Tunable      — weights and thresholds live in one place (this file).
• Side-effect free — scorer is a pure function; no I/O, no cache writes.
• Extensible   — new signal sources (LLM self-eval, user history, etc.)
                 can be added without touching the pipeline.

Score anatomy  (weighted sum, clamped to [0, 1])
────────────────────────────────────────────────
  semantic_sim   : cosine similarity of the cache hit          (0-1)
  success_rate   : historical success rate of the cached skill (0-1)
  risk_penalty   : negative score for high-risk actions        (0-1 subtracted)
  clarity_bonus  : command length / verb clarity boost         (0-1 additive, small)

  final = clip(
      w_sim   * semantic_sim
    + w_rate  * success_rate
    - w_risk  * risk_penalty
    + w_clar  * clarity_bonus,
    0, 1
  )

Confirmation thresholds
───────────────────────
  CONFIRM_THRESHOLD  = 0.60   (below → ask user)
  HIGH_RISK_ALWAYS   = True   (always ask for destructive actions, regardless of score)
"""

import logging
import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

logger = logging.getLogger("cecil.brain.confidence")


# ── Tunable weights / thresholds ──────────────────────────────────────────────

CONFIRM_THRESHOLD  = 0.60   # Score below this → request confirmation
HIGH_RISK_ALWAYS   = True   # Destructive actions always ask, even at score=1.0

# Signal weights (must sum to a reasonable total; final is clamped to [0,1])
W_SIM   = 0.45   # semantic similarity dominates
W_RATE  = 0.30   # historical success rate
W_RISK  = 0.50   # risk penalty (subtracted)
W_CLAR  = 0.15   # clarity bonus

# Risk levels
RISK_NONE        = 0.0
RISK_LOW         = 0.1
RISK_MEDIUM      = 0.35
RISK_HIGH        = 0.70
RISK_DESTRUCTIVE = 1.0


# ── Risk catalogue ─────────────────────────────────────────────────────────────

# (regex pattern, risk_level, label)
_RISK_PATTERNS: List[Tuple[str, float, str]] = [
    # Destructive / irreversible
    (r"\b(?:borra?|elimina?|destruye?|eliminar|delete|remove|rm\b|rmdir)\b",
     RISK_DESTRUCTIVE, "acción destructiva"),
    (r"\b(?:formatea?|format|wipe|overwrite|sobreescrib)\b",
     RISK_DESTRUCTIVE, "sobreescritura de datos"),
    (r"\b(?:apaga?|apagar|shutdown|poweroff|halt)\b",
     RISK_DESTRUCTIVE, "apagado del sistema"),

    # High risk
    (r"\b(?:cierra?|cerrar|kill|matar|close)\b",
     RISK_HIGH, "cierre de aplicación"),
    (r"\b(?:desinstala?|uninstall)\b",
     RISK_HIGH, "desinstalación"),
    (r"\b(?:sudo|su\b|chmod|chown)\b",
     RISK_HIGH, "operación privilegiada"),

    # Medium risk
    (r"\b(?:mueve?|mover|move|renombra?|rename)\b",
     RISK_MEDIUM, "mover/renombrar archivo"),
    (r"\b(?:instala?|install)\b",
     RISK_MEDIUM, "instalación de software"),
    (r"\b(?:sube?|subir|upload|publica?|deploy)\b",
     RISK_MEDIUM, "publicación/subida"),

    # Low risk
    (r"\b(?:guarda?|guardar|save)\b",
     RISK_LOW, "guardar archivo"),
]

# Verbs that indicate a clear, well-understood intent (clarity signal)
_CLEAR_VERB_PATTERNS = [
    r"\b(?:abre?|abrir|lanza?|lanzar|inicia?|iniciar|open|launch)\b",
    r"\b(?:escribe?|escribir|teclea?|teclear|type)\b",
    r"\b(?:ejecuta?|ejecutar|corre?|correr|run|execute)\b",
    r"\b(?:compila?|compilar|compile)\b",
    r"\b(?:navega?|navegar|navigate)\b",
]


# ── Data structures ────────────────────────────────────────────────────────────

@dataclass
class ConfidenceScore:
    """
    Full confidence assessment for a pending action.

    Attributes
    ──────────
    score          : composite confidence in [0, 1]
    needs_confirm  : True if the action should pause for user confirmation
    is_destructive : True if the action matches a destructive risk pattern
    explanation    : human-readable breakdown (shown in GUI log)
    risk_label     : short string describing the detected risk (or "")
    signals        : dict of individual signal values (for debugging/logging)
    """
    score:          float
    needs_confirm:  bool
    is_destructive: bool
    explanation:    str
    risk_label:     str = ""
    signals:        dict = field(default_factory=dict)


# ── Core scoring function ──────────────────────────────────────────────────────

def score_action(
    command: str,
    *,
    semantic_sim: float = 1.0,      # cosine similarity of cache hit (0-1)
    success_rate: float = 1.0,      # historical success rate of cached skill (0-1)
    is_cache_hit: bool = True,      # False → no cached skill available
    task_type: Optional[str] = None,# task_type from decomposer (or None)
) -> ConfidenceScore:
    """
    Compute a ConfidenceScore for a pending action.

    Parameters
    ──────────
    command      : The natural-language command (or sub-task command).
    semantic_sim : Cosine similarity of the best cache hit (1.0 if no cache used).
    success_rate : Historical execution success rate (1.0 if no cache used).
    is_cache_hit : Whether this action is being recalled from cache.
    task_type    : Structured task type from decomposer, if available.

    Returns
    ───────
    ConfidenceScore with score, needs_confirm, explanation, and signals.
    """
    cmd_lower = command.lower()

    # ── 1. Risk detection ──────────────────────────────
    risk_level = RISK_NONE
    risk_label = ""
    for pattern, level, label in _RISK_PATTERNS:
        if re.search(pattern, cmd_lower):
            if level > risk_level:
                risk_level = level
                risk_label = label

    # task_type overrides can sharpen risk detection
    if task_type in ("close_app",):
        risk_level = max(risk_level, RISK_HIGH)
        risk_label = risk_label or "cierre de aplicación"

    is_destructive = risk_level >= RISK_DESTRUCTIVE

    # ── 2. Clarity signal ──────────────────────────────
    has_clear_verb = any(
        re.search(p, cmd_lower) for p in _CLEAR_VERB_PATTERNS
    )
    word_count = len(cmd_lower.split())
    clarity = 1.0 if has_clear_verb else (0.5 if word_count >= 3 else 0.2)

    # ── 3. Cache signal adjustment ─────────────────────
    # No cache hit → we are planning fresh, treat semantic_sim and success_rate
    # as full (we trust L1-L3 planning) unless risk is high.
    if not is_cache_hit:
        semantic_sim = 1.0
        success_rate = 1.0

    # ── 4. Composite score ─────────────────────────────
    raw_score = (
        W_SIM  * semantic_sim
      + W_RATE * success_rate
      - W_RISK * risk_level
      + W_CLAR * clarity
    )
    score = max(0.0, min(1.0, raw_score))

    # ── 5. Confirmation decision ───────────────────────
    needs_confirm = (
        score < CONFIRM_THRESHOLD
        or (HIGH_RISK_ALWAYS and is_destructive)
    )

    # ── 6. Human-readable explanation ─────────────────
    parts = []
    if is_cache_hit:
        parts.append(f"similitud={semantic_sim:.0%}")
        parts.append(f"tasa_éxito={success_rate:.0%}")
    else:
        parts.append("plan nuevo (sin caché)")
    if risk_level > RISK_NONE:
        parts.append(f"riesgo={risk_label} ({risk_level:.0%})")
    if not has_clear_verb:
        parts.append("verbo ambiguo")
    parts.append(f"→ score={score:.2f}")
    if needs_confirm:
        parts.append("⚠ requiere confirmación")

    explanation = "  ".join(parts)

    signals = {
        "semantic_sim": round(semantic_sim, 3),
        "success_rate": round(success_rate, 3),
        "risk_level":   round(risk_level, 3),
        "clarity":      round(clarity, 3),
        "raw_score":    round(raw_score, 3),
        "final_score":  round(score, 3),
    }

    logger.debug(f"confidence({command!r}): {explanation}")

    return ConfidenceScore(
        score=score,
        needs_confirm=needs_confirm,
        is_destructive=is_destructive,
        explanation=explanation,
        risk_label=risk_label,
        signals=signals,
    )


# ── Convenience helpers ────────────────────────────────────────────────────────

def is_safe(command: str, **kwargs) -> bool:
    """True if the action does not need confirmation."""
    return not score_action(command, **kwargs).needs_confirm


def explain(command: str, **kwargs) -> str:
    """Return the human-readable explanation string."""
    return score_action(command, **kwargs).explanation
