"""
Cecil-Brain Task Cache.

A lightweight vector store that caches successful action plans.
When a similar command is received, the cache returns previous plans
to accelerate LLM reasoning and reduce latency.

Uses ChromaDB for vector similarity search (runs on CPU, ~50MB disk).
Falls back to simple keyword matching if ChromaDB is not available.
"""

import hashlib
import json
import logging
import os
from typing import Dict, List, Optional

logger = logging.getLogger("cecil.brain")


class TaskCache:
    """
    Caches successful task executions for future retrieval.

    Primary: ChromaDB (vector similarity search).
    Fallback: Simple JSON file with keyword matching.
    """

    def __init__(self, cache_dir: Optional[str] = None):
        """
        Initialize the task cache.

        Args:
            cache_dir: Directory to store cache data.
                       Defaults to ~/.cache/cecil/task_cache.
        """
        self._cache_dir = cache_dir or os.path.join(
            os.path.expanduser("~"), ".cache", "cecil", "task_cache"
        )
        os.makedirs(self._cache_dir, exist_ok=True)

        self._chroma_collection = None
        self._fallback_cache: List[Dict] = []
        self._fallback_file = os.path.join(self._cache_dir, "task_cache.json")

        self._init_backend()

    def _init_backend(self) -> None:
        """Initialize the best available cache backend."""
        try:
            import chromadb

            client = chromadb.PersistentClient(
                path=os.path.join(self._cache_dir, "chromadb")
            )
            self._chroma_collection = client.get_or_create_collection(
                name="cecil_tasks",
                metadata={"hnsw:space": "cosine"},
            )
            logger.info(
                f"TaskCache using ChromaDB "
                f"({self._chroma_collection.count()} cached tasks)"
            )
        except ImportError:
            logger.info(
                "ChromaDB not available, using simple JSON cache. "
                "Install with: pip install chromadb"
            )
            self._load_fallback()
        except Exception as e:
            logger.warning(f"ChromaDB init failed: {e}. Using fallback cache.")
            self._load_fallback()

    def _load_fallback(self) -> None:
        """Load the fallback JSON cache."""
        if os.path.isfile(self._fallback_file):
            try:
                with open(self._fallback_file, "r") as f:
                    self._fallback_cache = json.load(f)
                logger.info(
                    f"Fallback cache loaded: {len(self._fallback_cache)} tasks"
                )
            except Exception:
                self._fallback_cache = []
        else:
            self._fallback_cache = []

    def _save_fallback(self) -> None:
        """Save the fallback JSON cache."""
        try:
            with open(self._fallback_file, "w") as f:
                json.dump(self._fallback_cache, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save fallback cache: {e}")

    def store(
        self,
        command: str,
        actions: List[Dict],
        app_name: str = "",
        reasoning: str = "",
    ) -> None:
        """
        Store a successful task execution.

        Args:
            command: The user command that was executed.
            actions: The list of action steps that succeeded.
            app_name: The application context.
            reasoning: The LLM's reasoning for the plan.
        """
        task_id = hashlib.md5(
            f"{command}:{app_name}".encode()
        ).hexdigest()

        task_data = {
            "command": command,
            "actions": actions,
            "app_name": app_name,
            "reasoning": reasoning,
        }

        if self._chroma_collection is not None:
            try:
                self._chroma_collection.upsert(
                    ids=[task_id],
                    documents=[command],
                    metadatas=[{
                        "app_name": app_name,
                        "actions_json": json.dumps(actions, ensure_ascii=False),
                        "reasoning": reasoning,
                    }],
                )
                logger.debug(f"Stored task in ChromaDB: '{command}'")
            except Exception as e:
                logger.error(f"ChromaDB store error: {e}")
        else:
            # Fallback: simple list
            # Remove existing entry for same command+app
            self._fallback_cache = [
                t for t in self._fallback_cache
                if not (t.get("command") == command and t.get("app_name") == app_name)
            ]
            self._fallback_cache.append(task_data)
            self._save_fallback()
            logger.debug(f"Stored task in fallback cache: '{command}'")

    def find_similar(
        self, command: str, app_name: str = "", n_results: int = 3
    ) -> List[Dict]:
        """
        Find similar previously successful tasks.

        Args:
            command: The user command to search for.
            app_name: Optional application context filter.
            n_results: Number of results to return.

        Returns:
            List of task dictionaries with command, actions, reasoning.
        """
        if self._chroma_collection is not None:
            try:
                where_filter = None
                if app_name:
                    where_filter = {"app_name": app_name}

                results = self._chroma_collection.query(
                    query_texts=[command],
                    n_results=n_results,
                    where=where_filter,
                )

                tasks = []
                if results and results["documents"]:
                    for i, doc in enumerate(results["documents"][0]):
                        meta = results["metadatas"][0][i] if results["metadatas"] else {}
                        tasks.append({
                            "command": doc,
                            "actions": json.loads(
                                meta.get("actions_json", "[]")
                            ),
                            "app_name": meta.get("app_name", ""),
                            "reasoning": meta.get("reasoning", ""),
                        })
                return tasks

            except Exception as e:
                logger.error(f"ChromaDB query error: {e}")
                return []
        else:
            # Fallback: simple keyword matching
            command_words = set(command.lower().split())
            scored = []
            for task in self._fallback_cache:
                task_words = set(task.get("command", "").lower().split())
                overlap = len(command_words & task_words)
                if overlap > 0:
                    score = overlap / max(len(command_words), len(task_words))
                    if app_name and task.get("app_name") != app_name:
                        score *= 0.5  # Penalize different app
                    scored.append((score, task))

            scored.sort(key=lambda x: x[0], reverse=True)
            return [task for _, task in scored[:n_results]]

    @property
    def count(self) -> int:
        """Get the number of cached tasks."""
        if self._chroma_collection is not None:
            return self._chroma_collection.count()
        return len(self._fallback_cache)

    def clear(self) -> None:
        """Clear all cached tasks."""
        if self._chroma_collection is not None:
            try:
                # ChromaDB doesn't have a clear method, recreate collection
                import chromadb
                client = chromadb.PersistentClient(
                    path=os.path.join(self._cache_dir, "chromadb")
                )
                client.delete_collection("cecil_tasks")
                self._chroma_collection = client.create_collection(
                    name="cecil_tasks",
                    metadata={"hnsw:space": "cosine"},
                )
            except Exception as e:
                logger.error(f"ChromaDB clear error: {e}")
        else:
            self._fallback_cache = []
            self._save_fallback()
        logger.info("Task cache cleared")
