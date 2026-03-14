#!/usr/bin/env python3
"""
Phase 3: Task Decomposer — Complex Commands → Atomic Sub-Skills

Transforms a complex user command into an ordered list of atomic sub-tasks,
each of which can be:
  a) Directly resolved from the Skill Cache (instant)
  b) Planned fresh via L2/L3 LLM + vision (slow, then cached)

Design decisions:
  - Decomposition uses a lightweight rule-based system first (zero GPU cost)
  - LLM decomposition only if rules fail
  - Each sub-task is keyed by a canonical "task_type" for cache lookup
  - Composite skills are marked so they can be invalidated atomically

Example:
  Input:  "crea y compila un hello world en Rust"
  Output: [
    SubTask(task_type="open_terminal",     command="abre una terminal"),
    SubTask(task_type="create_file",       command="crea main.rs", args={"filename":"main.rs","lang":"rust"}),
    SubTask(task_type="type_in_terminal",  command='escribe fn main() { println!("Hello"); }', args={"text":"..."}),
    SubTask(task_type="run_command",       command="ejecuta rustc main.rs",  args={"cmd":"rustc main.rs"}),
    SubTask(task_type="run_command",       command="ejecuta ./main",         args={"cmd":"./main"}),
  ]
"""

import logging
import re
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple

logger = logging.getLogger("cecil.brain.decomposer")


# ── Data Structures ───────────────────────────────────────

@dataclass
class SubTask:
    """A single atomic sub-task produced by decomposition."""

    task_type: str          # Canonical type key — used for cache lookup
    command: str            # Natural-language command for this sub-task
    args: Dict              # Structured parameters (app, filename, text, cmd, url…)
    order: int = 0          # Execution order (0 = first)
    optional: bool = False  # If True, failure does not abort the whole plan
    depends_on: List[int] = field(default_factory=list)  # Indices of required predecessor tasks


@dataclass
class DecompositionResult:
    """Result from decomposing a complex command."""

    original_command: str
    subtasks: List[SubTask]
    is_composite: bool       # True if more than one sub-task
    decomposition_method: str  # "rules" | "llm" | "passthrough"
    confidence: float          # 0-1


# ── Rule-Based Patterns ───────────────────────────────────

# Each pattern: (regex, task_type, extractor_fn)
# extractor_fn(match) → dict of args
_OPEN_APP_PATTERNS = [
    (r"\babre?\b\s+(?:el\s+|la\s+|los?\s+)?(?:programa\s+|aplicaci[oó]n\s+)?(.+)", "open_app"),
    (r"\blanza\b\s+(.+)",                                                            "open_app"),
    (r"\binicia\b\s+(.+)",                                                           "open_app"),
    (r"\bopen\b\s+(.+)",                                                             "open_app"),
]

_TERMINAL_PATTERNS = [
    (r"\babre?\b\s+(?:una?\s+|la\s+)?terminal",    "open_terminal"),
    (r"\babre?\b\s+(?:una?\s+|la\s+)?consola",     "open_terminal"),
    (r"\bopen\b\s+(?:a\s+)?terminal",               "open_terminal"),
]

_CREATE_FILE_PATTERNS = [
    (r"crea\s+(?:un\s+)?(?:archivo\s+)?(?:llamado\s+)?(\S+\.?\w*)",    "create_file"),
    (r"create\s+(?:a\s+)?(?:file\s+)?(?:called\s+)?(\S+\.?\w*)",       "create_file"),
]

_RUN_COMMAND_PATTERNS = [
    (r"ejecuta\s+(?:el\s+comando\s+)?(.+)",     "run_command"),
    (r"corre\s+(?:el\s+comando\s+)?(.+)",       "run_command"),
    (r"run\s+(?:the\s+)?(?:command\s+)?(.+)",   "run_command"),
    (r"compila\s+(.+)",                          "compile"),
    (r"compile\s+(.+)",                          "compile"),
]

_TYPE_TEXT_PATTERNS = [
    (r"escribe\s+(.+)",                          "type_text"),
    (r"escr[ií]beme\s+(.+)",                     "type_text"),
    (r"type\s+(.+)",                             "type_text"),
    (r"teclea\s+(.+)",                           "type_text"),
]

_NAVIGATE_PATTERNS = [
    (r"ve?\s+a\s+(.+)",                          "navigate"),
    (r"navega\s+(?:a|hacia)\s+(.+)",             "navigate"),
    (r"abre?\s+(https?://\S+)",                  "navigate"),
    (r"go\s+to\s+(.+)",                          "navigate"),
]

_CLOSE_PATTERNS = [
    (r"cierra\s+(.+)",                           "close_app"),
    (r"close\s+(.+)",                            "close_app"),
]


# Language detection for "crea hello world en X"
_LANG_SNIPPETS: Dict[str, Tuple[str, str]] = {
    "rust":       ("main.rs",   'fn main() {\n    println!("Hello, world!");\n}\n'),
    "python":     ("main.py",   'print("Hello, world!")\n'),
    "c":          ("main.c",    '#include <stdio.h>\nint main() { printf("Hello, world!\\n"); return 0; }\n'),
    "c++":        ("main.cpp",  '#include <iostream>\nint main() { std::cout << "Hello, world!" << std::endl; return 0; }\n'),
    "go":         ("main.go",   'package main\nimport "fmt"\nfunc main() { fmt.Println("Hello, world!") }\n'),
    "javascript": ("index.js",  'console.log("Hello, world!");\n'),
    "java":       ("Main.java", 'public class Main { public static void main(String[] args) { System.out.println("Hello, world!"); } }\n'),
}

_COMPILE_COMMANDS: Dict[str, str] = {
    "rust":   "rustc main.rs && ./main",
    "c":      "gcc main.c -o main && ./main",
    "c++":    "g++ main.cpp -o main && ./main",
    "go":     "go run main.go",
    "java":   "javac Main.java && java Main",
    "python": "python3 main.py",
    "javascript": "node index.js",
}


# ── Decomposer ────────────────────────────────────────────

class TaskDecomposer:
    """
    Decomposes complex natural-language commands into ordered atomic sub-tasks.

    Strategy:
      1. Detect known composite patterns (hello world, project creation, etc.)
      2. Split conjunctions ("X y luego Y" → [X, Y])
      3. Apply rule-based atomic extractors to each segment
      4. Fall back to LLM decomposition if rules fail (optional)
    """

    # Composite triggers: if command matches these, decompose specifically
    _HELLO_WORLD_RE = re.compile(
        # "escribe hola mundo" (sin lenguaje) → type_text, no hello-world.
        # Con lenguaje explícito ("escribe un hello world en rust") → hello-world.
        r"(?:crea|hace?|genera|haz)\s+(?:un\s+)?(?:hola\s+mundo|hello\s+world|programa\s+b[áa]sico)"
        r"(?:\s+en\s+(\w+))?"
        r"|"
        r"(?:crea|hace?|escribe|genera|haz)\s+(?:un\s+)?(?:hola\s+mundo|hello\s+world|programa\s+b[áa]sico)"
        r"\s+en\s+(\w+)",
        re.IGNORECASE,
    )
    _CONJUNCTION_RE = re.compile(
        r"\s+(?:y\s+(?:después\s+)?(?:luego\s+)?|luego\s+|después\s+(?:de\s+esto\s+)?|then\s+|and\s+(?:then\s+)?)",
        re.IGNORECASE,
    )

    def decompose(self, command: str) -> DecompositionResult:
        """
        Decompose a command into ordered atomic sub-tasks.

        Returns DecompositionResult with subtasks + metadata.
        """
        command = command.strip()

        # 1. Check for known composite patterns first (highest priority)
        hw_match = self._HELLO_WORLD_RE.search(command)
        if hw_match:
            # Group 1: crea/haz/genera without mandatory language
            # Group 2: escribe/crea/… WITH mandatory "en <lang>"
            lang = (hw_match.group(1) or hw_match.group(2) or "python").lower()
            return self._decompose_hello_world(command, lang)

        # 2. Split by conjunctions
        segments = self._split_conjunctions(command)

        if len(segments) > 1:
            subtasks = []
            for i, segment in enumerate(segments):
                task = self._extract_single_task(segment.strip(), order=i)
                if task:
                    subtasks.append(task)
                else:
                    # Unknown segment → passthrough as a raw command
                    subtasks.append(SubTask(
                        task_type="raw_command",
                        command=segment.strip(),
                        args={"raw": segment.strip()},
                        order=i,
                    ))
            return DecompositionResult(
                original_command=command,
                subtasks=subtasks,
                is_composite=True,
                decomposition_method="rules",
                confidence=0.80,
            )

        # 3. Single-segment: try to extract atomic task
        task = self._extract_single_task(command, order=0)
        if task:
            return DecompositionResult(
                original_command=command,
                subtasks=[task],
                is_composite=False,
                decomposition_method="rules",
                confidence=0.90,
            )

        # 4. Unknown: passthrough (will go to L1/L2/L3 as usual)
        return DecompositionResult(
            original_command=command,
            subtasks=[SubTask(
                task_type="raw_command",
                command=command,
                args={"raw": command},
                order=0,
            )],
            is_composite=False,
            decomposition_method="passthrough",
            confidence=0.50,
        )

    def _split_conjunctions(self, command: str) -> List[str]:
        """Split 'X y luego Y' into ['X', 'Y']."""
        parts = self._CONJUNCTION_RE.split(command)
        return [p.strip() for p in parts if p and p.strip()]

    def _extract_single_task(self, segment: str, order: int = 0) -> Optional[SubTask]:
        """Match a single segment against known patterns."""

        seg_lower = segment.lower()

        # Terminal (check before open_app to avoid 'abre la consola' → open_app)
        for pattern, _ in _TERMINAL_PATTERNS:
            if re.search(pattern, seg_lower):
                return SubTask(
                    task_type="open_terminal",
                    command=segment,
                    args={},
                    order=order,
                )

        # Type text (check before open_app to avoid 'escribe X' → open_app)
        for pattern, task_type in _TYPE_TEXT_PATTERNS:
            m = re.search(pattern, seg_lower)
            if m:
                return SubTask(
                    task_type=task_type,
                    command=segment,
                    args={"text": m.group(1).strip()},
                    order=order,
                )

        # Open App
        for pattern, task_type in _OPEN_APP_PATTERNS:
            m = re.search(pattern, seg_lower)
            if m:
                return SubTask(
                    task_type=task_type,
                    command=segment,
                    args={"app": m.group(1).strip()},
                    order=order,
                )

        # Create File
        for pattern, task_type in _CREATE_FILE_PATTERNS:
            m = re.search(pattern, seg_lower)
            if m:
                return SubTask(
                    task_type=task_type,
                    command=segment,
                    args={"filename": m.group(1).strip()},
                    order=order,
                )

        # Run/Compile Command
        for pattern, task_type in _RUN_COMMAND_PATTERNS:
            m = re.search(pattern, seg_lower)
            if m:
                return SubTask(
                    task_type=task_type,
                    command=segment,
                    args={"cmd": m.group(1).strip()},
                    order=order,
                )

        # Navigate
        for pattern, task_type in _NAVIGATE_PATTERNS:
            m = re.search(pattern, seg_lower)
            if m:
                return SubTask(
                    task_type=task_type,
                    command=segment,
                    args={"target": m.group(1).strip()},
                    order=order,
                )

        # Close
        for pattern, task_type in _CLOSE_PATTERNS:
            m = re.search(pattern, seg_lower)
            if m:
                return SubTask(
                    task_type=task_type,
                    command=segment,
                    args={"app": m.group(1).strip()},
                    order=order,
                )

        return None

    def _decompose_hello_world(self, command: str, lang: str) -> DecompositionResult:
        """
        Specialized decomposition for 'hello world in X' pattern.

        Produces: open_terminal → create_file (with snippet) → run_command
        """
        lang_clean = lang.strip().lower()
        snippet_data = _LANG_SNIPPETS.get(lang_clean, _LANG_SNIPPETS["python"])
        filename, code = snippet_data
        run_cmd = _COMPILE_COMMANDS.get(lang_clean, f"python3 {filename}")

        subtasks = [
            SubTask(
                task_type="open_terminal",
                command="abre una terminal",
                args={},
                order=0,
            ),
            SubTask(
                task_type="create_file",
                command=f"crea {filename} con el código",
                args={"filename": filename, "content": code, "lang": lang_clean},
                order=1,
                depends_on=[0],
            ),
            SubTask(
                task_type="run_command",
                command=f"ejecuta {run_cmd}",
                args={"cmd": run_cmd},
                order=2,
                depends_on=[1],
            ),
        ]

        logger.info(f"Hello-world decomposition: lang={lang_clean}, {len(subtasks)} steps")
        return DecompositionResult(
            original_command=command,
            subtasks=subtasks,
            is_composite=True,
            decomposition_method="rules",
            confidence=0.95,
        )


# Module-level singleton
_decomposer: Optional[TaskDecomposer] = None


def get_decomposer() -> TaskDecomposer:
    """Get (or lazily create) the global TaskDecomposer instance."""
    global _decomposer
    if _decomposer is None:
        _decomposer = TaskDecomposer()
    return _decomposer


def decompose(command: str) -> DecompositionResult:
    """Convenience function: decompose a command into sub-tasks."""
    return get_decomposer().decompose(command)
