"""
Cecil-Brain Skill Cache.

Stores semantic action plans (skills) indexed by command embeddings.
Enables rapid re-execution of previously successful tasks without re-planning.

Key principle: Cache DECISIONS (semantic steps), not ACTIONS (coordinates/screenshots).
- Cached: {intent: "click_button", target_label: "Compile", fallback_key: "F5"}
- NOT cached: coordinates, screenshots, app-specific layouts

Backend options:
  - Primary: SQLite + embeddings (CPU-based similarity search)
  - Fallback: JSON file with simple keyword matching
"""

import hashlib
import json
import logging
import os
import sqlite3
import threading
from dataclasses import dataclass, asdict, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("cecil.brain.cache")


@dataclass
class SemanticStep:
    """A semantic action step (NOT tied to coordinates or screenshots)."""

    intent: str  # "click_button", "type_text", "key_press", "launch_app", etc.
    target: Optional[str] = None  # Semantic target: label, button name, app name
    text: Optional[str] = None  # Text to type (if intent is "type_text")
    key: Optional[str] = None  # Key combination (if intent is "key_press")
    app: Optional[str] = None  # Target app (if intent is "launch_app")
    fallback: Optional[str] = None  # Fallback key combo (if primary target fails)
    metadata: Dict = field(default_factory=dict)  # App context, etc.

    def to_dict(self) -> Dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: Dict) -> "SemanticStep":
        return SemanticStep(**{k: v for k, v in d.items() if k != "metadata"})


@dataclass
class CachedSkill:
    """A cached skill: reusable semantic plan."""

    id: str  # Unique hash of the skill
    command: str  # Original user command (e.g., "abre Firefox")
    command_embedding: List[float]  # Embedding of the command (for similarity search)
    steps: List[SemanticStep]  # Semantic action steps (no coordinates)
    app_context: str = ""  # App that was active during planning (e.g., "desktop")
    success_count: int = 0  # Number of successful executions
    failure_count: int = 0  # Number of failed executions
    last_executed: Optional[str] = None  # ISO datetime of last execution
    last_validated: Optional[str] = None  # ISO datetime of last validation check
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    composite: bool = False  # Is this a composite skill (made of sub-skills)?

    def to_dict(self) -> Dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: Dict) -> "CachedSkill":
        steps_data = d.pop("steps", [])
        steps = [SemanticStep.from_dict(s) if isinstance(s, dict) else s for s in steps_data]
        d["steps"] = steps
        return CachedSkill(**d)

    @property
    def success_rate(self) -> float:
        """Return success rate (0-1)."""
        total = self.success_count + self.failure_count
        return self.success_count / total if total > 0 else 0.0


class SkillCache:
    """
    Semantic skill cache with SQLite backend.

    Primary: similarity search via embeddings
    Fallback: keyword matching
    """

    def __init__(self, cache_dir: Optional[str] = None):
        """
        Initialize the skill cache.

        Args:
            cache_dir: Directory for cache storage. Defaults to ~/.cache/cecil/skills.
        """
        self._cache_dir = cache_dir or os.path.join(
            os.path.expanduser("~"), ".cache", "cecil", "skills"
        )
        os.makedirs(self._cache_dir, exist_ok=True)

        self._db_path = os.path.join(self._cache_dir, "skills.db")
        self._json_fallback_path = os.path.join(self._cache_dir, "skills_fallback.json")
        self._lock = threading.RLock()

        self._use_sqlite = self._init_sqlite()
        if not self._use_sqlite:
            self._fallback_skills: Dict[str, CachedSkill] = {}
            self._load_fallback()

    def _init_sqlite(self) -> bool:
        """Initialize SQLite database. Returns True if successful."""
        try:
            conn = sqlite3.connect(self._db_path)
            cursor = conn.cursor()

            # Create table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS skills (
                    id TEXT PRIMARY KEY,
                    command TEXT NOT NULL,
                    command_embedding BLOB,
                    steps JSON NOT NULL,
                    app_context TEXT,
                    success_count INTEGER DEFAULT 0,
                    failure_count INTEGER DEFAULT 0,
                    last_executed TEXT,
                    last_validated TEXT,
                    created_at TEXT NOT NULL,
                    composite BOOLEAN DEFAULT 0
                )
                """
            )

            # Create index on command (for keyword search)
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_command ON skills(command)"
            )

            conn.commit()
            conn.close()
            logger.info(f"SQLite cache initialized: {self._db_path}")
            return True

        except Exception as e:
            logger.warning(f"SQLite init failed: {e}, using fallback JSON")
            return False

    def _load_fallback(self):
        """Load fallback JSON cache."""
        if os.path.isfile(self._json_fallback_path):
            try:
                with open(self._json_fallback_path) as f:
                    data = json.load(f)
                    self._fallback_skills = {
                        k: CachedSkill.from_dict(v) for k, v in data.items()
                    }
                    logger.info(f"Loaded {len(self._fallback_skills)} skills from fallback")
            except Exception as e:
                logger.warning(f"Fallback load failed: {e}")
                self._fallback_skills = {}

    def save(self, skill: CachedSkill) -> None:
        """
        Save a skill to the cache.

        Args:
            skill: The CachedSkill to save.
        """
        with self._lock:
            if self._use_sqlite:
                self._save_sqlite(skill)
            else:
                self._save_fallback(skill)

    def _save_sqlite(self, skill: CachedSkill) -> None:
        """Save skill to SQLite."""
        try:
            conn = sqlite3.connect(self._db_path)
            cursor = conn.cursor()

            steps_json = json.dumps([s.to_dict() for s in skill.steps])
            embedding_blob = (
                json.dumps(skill.command_embedding).encode()
                if skill.command_embedding
                else None
            )

            cursor.execute(
                """
                INSERT OR REPLACE INTO skills
                (id, command, command_embedding, steps, app_context, success_count,
                 failure_count, last_executed, last_validated, created_at, composite)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    skill.id,
                    skill.command,
                    embedding_blob,
                    steps_json,
                    skill.app_context,
                    skill.success_count,
                    skill.failure_count,
                    skill.last_executed,
                    skill.last_validated,
                    skill.created_at,
                    skill.composite,
                ),
            )

            conn.commit()
            conn.close()
            logger.info(f"Saved skill: {skill.id} ({skill.command})")

        except Exception as e:
            logger.error(f"SQLite save failed: {e}")

    def _save_fallback(self, skill: CachedSkill) -> None:
        """Save skill to JSON fallback."""
        try:
            self._fallback_skills[skill.id] = skill
            with open(self._json_fallback_path, "w") as f:
                data = {k: v.to_dict() for k, v in self._fallback_skills.items()}
                json.dump(data, f, indent=2, default=str)
            logger.info(f"Saved skill (fallback): {skill.id} ({skill.command})")
        except Exception as e:
            logger.error(f"Fallback save failed: {e}")

    def query(
        self, command: str, threshold: float = 0.85
    ) -> Optional[CachedSkill]:
        """
        Query the cache for a similar skill.

        Args:
            command: User command to search for.
            threshold: Confidence threshold (0-1). Default 0.85.

        Returns:
            Matching CachedSkill if found, else None.
        """
        with self._lock:
            if self._use_sqlite:
                return self._query_sqlite(command, threshold)
            else:
                return self._query_fallback(command, threshold)

    def _query_sqlite(self, command: str, threshold: float) -> Optional[CachedSkill]:
        """Query SQLite by keyword matching (simple fallback)."""
        try:
            conn = sqlite3.connect(self._db_path)
            cursor = conn.cursor()

            # Simple keyword search (not embedding-based yet)
            # TODO: integrate with sentence-transformers for real similarity
            keywords = command.lower().split()
            if not keywords:
                return None
            
            placeholders = " OR ".join(
                ["command LIKE ?" for _ in keywords]
            )
            query_terms = [f"%{kw}%" for kw in keywords]

            cursor.execute(
                f"""
                SELECT * FROM skills
                WHERE {placeholders}
                ORDER BY success_count DESC, created_at DESC
                LIMIT 1
                """,
                query_terms,
            )

            row = cursor.fetchone()
            conn.close()

            if not row:
                return None

            # Parse row back to CachedSkill
            skill = self._row_to_skill(row)
            # NOTE: threshold parameter reserved for embedding-based similarity
            # For now, keyword matches are accepted regardless of success_rate
            # Success rate is used for ordering/selection, not filtering
            logger.info(f"Cache hit: {skill.id} (rate: {skill.success_rate:.0%})")
            return skill

        except Exception as e:
            logger.error(f"SQLite query failed: {e}")
            return None

    def _query_fallback(self, command: str, threshold: float) -> Optional[CachedSkill]:
        """Query fallback JSON by keyword overlap (Jaccard similarity)."""
        keywords = set(command.lower().split())
        best_match = None
        best_overlap = 0

        for skill in self._fallback_skills.values():
            skill_keywords = set(skill.command.lower().split())
            if not keywords or not skill_keywords:
                continue
            
            # Jaccard similarity: intersection / union
            overlap = len(keywords & skill_keywords) / len(keywords | skill_keywords)

            # NOTE: threshold parameter reserved for embedding-based similarity
            # For now, highest keyword overlap is selected regardless of success_rate
            # Success rate is used for ordering/selection, not filtering
            if overlap > best_overlap:
                best_match = skill
                best_overlap = overlap

        if best_match:
            logger.info(f"Cache hit (fallback): {best_match.id} (overlap: {best_overlap:.0%})")
            return best_match

        return None

    def _row_to_skill(self, row: Tuple) -> CachedSkill:
        """Convert SQLite row to CachedSkill."""
        (
            id_,
            command,
            embedding_blob,
            steps_json,
            app_context,
            success_count,
            failure_count,
            last_executed,
            last_validated,
            created_at,
            composite,
        ) = row

        embedding = (
            json.loads(embedding_blob.decode()) if embedding_blob else []
        )
        steps_data = json.loads(steps_json)
        steps = [SemanticStep.from_dict(s) for s in steps_data]

        return CachedSkill(
            id=id_,
            command=command,
            command_embedding=embedding,
            steps=steps,
            app_context=app_context or "",
            success_count=success_count,
            failure_count=failure_count,
            last_executed=last_executed,
            last_validated=last_validated,
            created_at=created_at,
            composite=bool(composite),
        )

    def record_success(self, skill_id: str) -> None:
        """Record successful execution of a skill."""
        with self._lock:
            if self._use_sqlite:
                self._record_success_sqlite(skill_id)
            else:
                self._record_success_fallback(skill_id)

    def _record_success_sqlite(self, skill_id: str) -> None:
        """Record success in SQLite."""
        try:
            conn = sqlite3.connect(self._db_path)
            cursor = conn.cursor()
            now = datetime.utcnow().isoformat()

            cursor.execute(
                """
                UPDATE skills
                SET success_count = success_count + 1,
                    last_executed = ?
                WHERE id = ?
                """,
                (now, skill_id),
            )

            conn.commit()
            conn.close()

        except Exception as e:
            logger.error(f"Record success failed: {e}")

    def _record_success_fallback(self, skill_id: str) -> None:
        """Record success in fallback."""
        if skill_id in self._fallback_skills:
            skill = self._fallback_skills[skill_id]
            skill.success_count += 1
            skill.last_executed = datetime.utcnow().isoformat()
            self._save_fallback(skill)

    def record_failure(self, skill_id: str, failed_step: int = -1) -> None:
        """
        Record failed execution of a skill.

        Args:
            skill_id: ID of the skill.
            failed_step: Index of the step that failed (-1 = unknown).
        """
        with self._lock:
            if self._use_sqlite:
                self._record_failure_sqlite(skill_id, failed_step)
            else:
                self._record_failure_fallback(skill_id, failed_step)

    def _record_failure_sqlite(self, skill_id: str, failed_step: int) -> None:
        """Record failure in SQLite."""
        try:
            conn = sqlite3.connect(self._db_path)
            cursor = conn.cursor()

            cursor.execute(
                """
                UPDATE skills
                SET failure_count = failure_count + 1
                WHERE id = ?
                """,
                (skill_id,),
            )

            conn.commit()
            conn.close()

        except Exception as e:
            logger.error(f"Record failure failed: {e}")

    def _record_failure_fallback(self, skill_id: str, failed_step: int) -> None:
        """Record failure in fallback."""
        if skill_id in self._fallback_skills:
            skill = self._fallback_skills[skill_id]
            skill.failure_count += 1
            self._save_fallback(skill)

    def list_skills(self, app_context: Optional[str] = None) -> List[CachedSkill]:
        """List all cached skills, optionally filtered by app context."""
        with self._lock:
            if self._use_sqlite:
                return self._list_skills_sqlite(app_context)
            else:
                return self._list_skills_fallback(app_context)

    def _list_skills_sqlite(self, app_context: Optional[str]) -> List[CachedSkill]:
        """List skills from SQLite."""
        try:
            conn = sqlite3.connect(self._db_path)
            cursor = conn.cursor()

            if app_context:
                cursor.execute(
                    "SELECT * FROM skills WHERE app_context = ? ORDER BY success_count DESC",
                    (app_context,),
                )
            else:
                cursor.execute("SELECT * FROM skills ORDER BY success_count DESC")

            rows = cursor.fetchall()
            conn.close()

            return [self._row_to_skill(row) for row in rows]

        except Exception as e:
            logger.error(f"List skills failed: {e}")
            return []

    def _list_skills_fallback(self, app_context: Optional[str]) -> List[CachedSkill]:
        """List skills from fallback."""
        skills = list(self._fallback_skills.values())
        if app_context:
            skills = [s for s in skills if s.app_context == app_context]
        return sorted(skills, key=lambda s: s.success_count, reverse=True)

    def invalidate(self, skill_id: str) -> None:
        """Mark a skill as invalid (e.g., after validation failure)."""
        with self._lock:
            if self._use_sqlite:
                self._invalidate_sqlite(skill_id)
            else:
                self._invalidate_fallback(skill_id)

    def _invalidate_sqlite(self, skill_id: str) -> None:
        """Invalidate in SQLite."""
        try:
            conn = sqlite3.connect(self._db_path)
            cursor = conn.cursor()

            # Set failure count high to reduce selection priority
            cursor.execute(
                "UPDATE skills SET failure_count = failure_count + 100 WHERE id = ?",
                (skill_id,),
            )

            conn.commit()
            conn.close()

        except Exception as e:
            logger.error(f"Invalidate failed: {e}")

    def _invalidate_fallback(self, skill_id: str) -> None:
        """Invalidate in fallback."""
        if skill_id in self._fallback_skills:
            self._fallback_skills[skill_id].failure_count += 100
            self._save_fallback(self._fallback_skills[skill_id])

    def clear(self) -> None:
        """Clear all cached skills (dangerous!)."""
        with self._lock:
            if self._use_sqlite:
                try:
                    conn = sqlite3.connect(self._db_path)
                    cursor = conn.cursor()
                    cursor.execute("DELETE FROM skills")
                    conn.commit()
                    conn.close()
                    logger.warning("Cache cleared (SQLite)")
                except Exception as e:
                    logger.error(f"Clear failed: {e}")
            else:
                self._fallback_skills = {}
                if os.path.isfile(self._json_fallback_path):
                    os.remove(self._json_fallback_path)
                logger.warning("Cache cleared (fallback)")

    @property
    def count(self) -> int:
        """Return number of cached skills."""
        with self._lock:
            if self._use_sqlite:
                try:
                    conn = sqlite3.connect(self._db_path)
                    cursor = conn.cursor()
                    cursor.execute("SELECT COUNT(*) FROM skills")
                    count = cursor.fetchone()[0]
                    conn.close()
                    return count
                except Exception:
                    return 0
            else:
                return len(self._fallback_skills)
