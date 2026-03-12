"""
Phase 7 — Self-Correction Loop
================================
Provides retry/escalation logic for the execution pipeline.

When a sub-task or layer execution fails, ``SelfCorrector.suggest()`` decides
the best recovery strategy without repeating the same futile action.

Strategies (``RetryStrategy``)
-------------------------------
RETRY_SAME        – run the identical action again (transient glitch)
TRY_ALTERNATIVE   – substitute an equivalent command/app
ESCALATE_L2       – hand off to the LLM layer
ESCALATE_L3       – hand off to the Vision+LLM layer
ABORT             – no recovery possible; surface a clear error

``CorrectionResult``
--------------------
Returned by ``suggest()``.  When strategy == TRY_ALTERNATIVE the
``alternative_command`` / ``alternative_args`` fields carry the substitute.

``SelfCorrector``
-----------------
Stateless helper; call ``suggest()`` for every failure.
The caller decides whether to honour the suggestion and tracks ``attempt``.

Usage example::

    corrector = SelfCorrector()
    for attempt in range(SelfCorrector.MAX_ATTEMPTS):
        ok = executor.launch_app(app)
        if ok:
            break
        result = corrector.suggest("open_terminal", {"app": app},
                                   attempt=attempt, error="launch_failed")
        if result.strategy == RetryStrategy.TRY_ALTERNATIVE:
            app = result.alternative_args.get("app", app)
        elif result.strategy == RetryStrategy.ABORT:
            break
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


# ── Strategy enum ─────────────────────────────────────────────────────────────

class RetryStrategy(Enum):
    RETRY_SAME       = "retry_same"
    TRY_ALTERNATIVE  = "try_alternative"
    ESCALATE_L2      = "escalate_l2"
    ESCALATE_L3      = "escalate_l3"
    ABORT            = "abort"


# ── Result dataclass ───────────────────────────────────────────────────────────

@dataclass
class CorrectionResult:
    strategy:            RetryStrategy
    reason:              str
    alternative_command: Optional[str]       = None
    alternative_args:    Dict[str, str]      = field(default_factory=dict)

    @property
    def is_terminal(self) -> bool:
        return self.strategy == RetryStrategy.ABORT

    @property
    def needs_escalation(self) -> bool:
        return self.strategy in (RetryStrategy.ESCALATE_L2, RetryStrategy.ESCALATE_L3)


# ── Terminal / app fallback tables ────────────────────────────────────────────

# Ordered preference list for terminal emulators.
# The caller (open_terminal fast-path) iterates this sequence.
TERMINAL_FALLBACKS: List[str] = [
    "kitty",
    "gnome-terminal",
    "xterm",
    "foot",
    "konsole",
    "alacritty",
    "wezterm",
    "xfce4-terminal",
    "bash",          # last resort: bare shell (no graphical frame)
]

# Common aliases / alternative names for popular applications.
# Maps canonical name → list of alternatives (in preference order).
APP_ALIASES: Dict[str, List[str]] = {
    # Browsers
    "firefox":          ["firefox-esr", "firefox-bin", "iceweasel"],
    "chrome":           ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser"],
    "chromium":         ["chromium-browser", "google-chrome", "google-chrome-stable"],
    "brave":            ["brave-browser"],
    # Code editors
    "code":             ["code-insiders", "codium", "vscodium"],
    "codium":           ["vscodium", "code"],
    "vscodium":         ["codium", "code"],
    # File managers
    "nautilus":         ["thunar", "dolphin", "nemo", "pcmanfm"],
    "thunar":           ["nautilus", "dolphin", "nemo", "pcmanfm"],
    "dolphin":          ["nautilus", "thunar", "nemo", "pcmanfm"],
    # Text editors
    "gedit":            ["mousepad", "kate", "pluma", "xed"],
    "kate":             ["gedit", "mousepad", "pluma"],
    "mousepad":         ["gedit", "kate", "pluma"],
    # Terminals (used for open_app fallbacks as well)
    "kitty":            ["gnome-terminal", "xterm", "foot", "alacritty"],
    "gnome-terminal":   ["kitty", "xterm", "foot", "alacritty"],
    "alacritty":        ["kitty", "gnome-terminal", "xterm"],
    # Video / media
    "vlc":              ["mpv", "totem", "celluloid"],
    "mpv":              ["vlc", "totem"],
    # Image viewers
    "eog":              ["feh", "viewnior", "ristretto", "gwenview"],
    "feh":              ["eog", "viewnior"],
}

# Task types that can be retried at the same layer on transient failures.
_RETRYABLE_SAME: frozenset = frozenset({
    "run_command", "compile", "type_text", "press_key",
})

# Task types that should escalate to L2 after one failure.
_ESCALATE_TO_L2: frozenset = frozenset({
    "navigate", "create_file",
})


# ── Core corrector ─────────────────────────────────────────────────────────────

class SelfCorrector:
    """
    Stateless advisor for the execution pipeline.

    Call ``suggest()`` after every failed action to receive a
    ``CorrectionResult`` that tells the caller *what to try next*.
    The caller is responsible for tracking ``attempt`` counts.
    """

    MAX_ATTEMPTS: int = 3  # total attempts before ABORT (including the first)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def suggest(
        self,
        task_type: str,
        args: Dict[str, str],
        attempt: int,
        error: str = "unknown",
    ) -> CorrectionResult:
        """
        Return a recovery strategy for the given failure.

        Parameters
        ----------
        task_type : str
            The task type string, e.g. ``"open_terminal"``, ``"open_app"``.
        args : dict
            The args dict from the sub-task (``{"app": "kitty"}``, etc.).
        attempt : int
            0-based attempt index.  0 = first failure, 1 = second, etc.
        error : str
            Short error tag: ``"launch_failed"``, ``"not_found"``,
            ``"timeout"``, etc.

        Returns
        -------
        CorrectionResult
        """
        # Hard cap: never exceed MAX_ATTEMPTS total
        if attempt >= self.MAX_ATTEMPTS - 1:
            return CorrectionResult(
                strategy=RetryStrategy.ABORT,
                reason=f"Máximo de intentos alcanzado ({self.MAX_ATTEMPTS}) para '{task_type}'",
            )

        handler = self._HANDLERS.get(task_type, self._default_suggest)
        result = handler(self, task_type, args, attempt, error)
        logger.debug(
            "self_correction: task=%s attempt=%d error=%s → strategy=%s reason=%s",
            task_type, attempt, error, result.strategy.value, result.reason,
        )
        return result

    def next_terminal(self, current: str) -> Optional[str]:
        """Return the next terminal to try after ``current``."""
        try:
            idx = TERMINAL_FALLBACKS.index(current)
        except ValueError:
            idx = -1
        nxt = idx + 1
        return TERMINAL_FALLBACKS[nxt] if nxt < len(TERMINAL_FALLBACKS) else None

    def next_app(self, app: str) -> Optional[str]:
        """Return the first alternative for ``app``, or None."""
        candidates = APP_ALIASES.get(app.lower(), [])
        return candidates[0] if candidates else None

    def alternatives_for(self, app: str) -> List[str]:
        """Return all known alternatives for ``app``."""
        return list(APP_ALIASES.get(app.lower(), []))

    # ------------------------------------------------------------------
    # Private handlers (one per task type)
    # ------------------------------------------------------------------

    def _open_terminal_suggest(
        self,
        task_type: str,
        args: Dict[str, str],
        attempt: int,
        error: str,
    ) -> CorrectionResult:
        """Cycle through TERMINAL_FALLBACKS."""
        current = args.get("app", TERMINAL_FALLBACKS[0])
        nxt = self.next_terminal(current)
        if nxt is not None:
            return CorrectionResult(
                strategy=RetryStrategy.TRY_ALTERNATIVE,
                reason=f"'{current}' no disponible → intentando '{nxt}'",
                alternative_command=nxt,
                alternative_args={"app": nxt},
            )
        # Ran out of terminals → escalate to L2 so LLM can figure it out
        return CorrectionResult(
            strategy=RetryStrategy.ESCALATE_L2,
            reason="Ningún terminal disponible — escalando a LLM",
        )

    def _open_app_suggest(
        self,
        task_type: str,
        args: Dict[str, str],
        attempt: int,
        error: str,
    ) -> CorrectionResult:
        """Try app aliases; escalate to L2 after exhausting them."""
        app = args.get("app", "")
        alts = self.alternatives_for(app)
        # Pick the next untried alternative based on attempt count
        alt_idx = attempt  # attempt=0 → alts[0], attempt=1 → alts[1], …
        if alt_idx < len(alts):
            alt = alts[alt_idx]
            return CorrectionResult(
                strategy=RetryStrategy.TRY_ALTERNATIVE,
                reason=f"'{app}' no encontrado → intentando alias '{alt}'",
                alternative_command=alt,
                alternative_args={"app": alt},
            )
        return CorrectionResult(
            strategy=RetryStrategy.ESCALATE_L2,
            reason=f"'{app}' y sus aliases agotados — escalando a LLM",
        )

    def _run_command_suggest(
        self,
        task_type: str,
        args: Dict[str, str],
        attempt: int,
        error: str,
    ) -> CorrectionResult:
        """
        Commands can fail transiently (focus race, clipboard lag).
        Retry once; then escalate.
        """
        if attempt == 0:
            return CorrectionResult(
                strategy=RetryStrategy.RETRY_SAME,
                reason="Error transitorio al escribir el comando — reintentando",
            )
        return CorrectionResult(
            strategy=RetryStrategy.ESCALATE_L2,
            reason="run_command falló dos veces — escalando a LLM",
        )

    def _compile_suggest(
        self,
        task_type: str,
        args: Dict[str, str],
        attempt: int,
        error: str,
    ) -> CorrectionResult:
        # Compilation errors are usually semantic → LLM is more helpful
        if attempt == 0:
            return CorrectionResult(
                strategy=RetryStrategy.RETRY_SAME,
                reason="Error de escritura en compilación — reintentando",
            )
        return CorrectionResult(
            strategy=RetryStrategy.ESCALATE_L2,
            reason="Compilación falló — escalando a LLM para diagnóstico",
        )

    def _type_text_suggest(
        self,
        task_type: str,
        args: Dict[str, str],
        attempt: int,
        error: str,
    ) -> CorrectionResult:
        """Typing errors are nearly always transient (focus, ydotool lag)."""
        if attempt == 0:
            return CorrectionResult(
                strategy=RetryStrategy.RETRY_SAME,
                reason="Error al escribir texto — reintentando (posible lag de input)",
            )
        return CorrectionResult(
            strategy=RetryStrategy.ESCALATE_L3,
            reason="type_text falló repetidamente — escalando a Vision+LLM",
        )

    def _create_file_suggest(
        self,
        task_type: str,
        args: Dict[str, str],
        attempt: int,
        error: str,
    ) -> CorrectionResult:
        return CorrectionResult(
            strategy=RetryStrategy.ESCALATE_L2,
            reason="Creación de archivo falló — escalando a LLM",
        )

    def _navigate_suggest(
        self,
        task_type: str,
        args: Dict[str, str],
        attempt: int,
        error: str,
    ) -> CorrectionResult:
        return CorrectionResult(
            strategy=RetryStrategy.ESCALATE_L2,
            reason="Navegación falló — escalando a LLM",
        )

    def _close_app_suggest(
        self,
        task_type: str,
        args: Dict[str, str],
        attempt: int,
        error: str,
    ) -> CorrectionResult:
        if attempt == 0:
            return CorrectionResult(
                strategy=RetryStrategy.RETRY_SAME,
                reason="Cierre de ventana falló — reintentando",
            )
        return CorrectionResult(
            strategy=RetryStrategy.ESCALATE_L3,
            reason="No se pudo cerrar la app — escalando a Vision+LLM",
        )

    def _default_suggest(
        self,
        task_type: str,
        args: Dict[str, str],
        attempt: int,
        error: str,
    ) -> CorrectionResult:
        """Fallback: escalate to L2 on first failure, L3 on second."""
        if attempt == 0:
            return CorrectionResult(
                strategy=RetryStrategy.ESCALATE_L2,
                reason=f"'{task_type}' falló — escalando a LLM",
            )
        return CorrectionResult(
            strategy=RetryStrategy.ESCALATE_L3,
            reason=f"'{task_type}' falló en L2 también — escalando a Vision+LLM",
        )

    # Dispatch table: task_type → handler method
    _HANDLERS = {
        "open_terminal": _open_terminal_suggest,
        "open_app":      _open_app_suggest,
        "run_command":   _run_command_suggest,
        "compile":       _compile_suggest,
        "type_text":     _type_text_suggest,
        "create_file":   _create_file_suggest,
        "navigate":      _navigate_suggest,
        "close_app":     _close_app_suggest,
    }


# ── Layer-level helpers (used by the pipeline) ────────────────────────────────

def suggest_layer_escalation(
    current_layer: int,
    attempt: int,
    error: str = "failed",
    max_attempts: int = 2,
) -> CorrectionResult:
    """
    Return an escalation strategy for layer-level failures.

    ``current_layer`` should be 1 (Intent Parser) or 2 (LLM).
    Layer 3 failures always abort.
    """
    if attempt >= max_attempts - 1:
        return CorrectionResult(
            strategy=RetryStrategy.ABORT,
            reason=f"L{current_layer} superó el máximo de intentos",
        )

    if current_layer == 1:
        return CorrectionResult(
            strategy=RetryStrategy.ESCALATE_L2,
            reason=f"L1 falló ({error}) → escalando a LLM",
        )
    if current_layer == 2:
        return CorrectionResult(
            strategy=RetryStrategy.ESCALATE_L3,
            reason=f"L2 falló ({error}) → escalando a Vision+LLM",
        )
    # Layer 3 or unknown → abort
    return CorrectionResult(
        strategy=RetryStrategy.ABORT,
        reason=f"L{current_layer} falló y no hay capa superior — abortando",
    )
