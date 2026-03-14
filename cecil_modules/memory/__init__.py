"""
Memory Module - Phase 2.4

Implements persistent memory, skill cache, and learning capabilities.
Integrates with OpenClaw skill cache and provides cross-session learning.
"""

import logging
import time
import json
import sqlite3
import threading
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict, field
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger("cecil.memory")


@dataclass
class MemoryEntry:
    """Generic memory entry with metadata."""
    id: str
    type: str  # "skill", "execution", "preference", "context"
    content: Dict
    timestamp: float
    access_count: int = 0
    last_accessed: float = field(default_factory=time.time)
    tags: List[str] = field(default_factory=list)
    importance: float = 0.5  # 0.0 to 1.0
    expires_at: Optional[float] = None


@dataclass
class ExecutionMemory:
    """Memory of plan execution for learning."""
    plan_id: str
    command: str
    plan_source: str
    actions: List[Dict]
    success: bool
    execution_time: float
    error_message: Optional[str] = None
    context: Dict = field(default_factory=dict)
    feedback_score: Optional[float] = None  # User feedback 0.0-1.0


class PersistentMemory:
    """
    Persistent memory system with SQLite backend.
    Stores skills, executions, preferences, and context.
    """
    
    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = Path.home() / ".cache" / "cecil" / "memory.db"
        
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        self._initialize_database()
        self._cleanup_expired_entries()
        
        self.stats = {
            "total_entries": 0,
            "skill_entries": 0,
            "execution_entries": 0,
            "cache_hits": 0,
            "cache_misses": 0
        }
    
    def _initialize_database(self):
        """Initialize database schema."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS memory_entries (
                    id TEXT PRIMARY KEY,
                    type TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    access_count INTEGER DEFAULT 0,
                    last_accessed REAL NOT NULL,
                    tags TEXT,
                    importance REAL DEFAULT 0.5,
                    expires_at REAL
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS execution_memory (
                    plan_id TEXT PRIMARY KEY,
                    command TEXT NOT NULL,
                    plan_source TEXT NOT NULL,
                    actions TEXT NOT NULL,
                    success BOOLEAN NOT NULL,
                    execution_time REAL NOT NULL,
                    error_message TEXT,
                    context TEXT,
                    feedback_score REAL,
                    timestamp REAL NOT NULL
                )
            """)
            
            # Create indexes for performance
            conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_type ON memory_entries(type)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_timestamp ON memory_entries(timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_importance ON memory_entries(importance)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_execution_success ON execution_memory(success)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_execution_command ON execution_memory(command)")
    
    def store_memory(self, entry: MemoryEntry) -> bool:
        """Store a memory entry."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO memory_entries 
                    (id, type, content, timestamp, access_count, last_accessed, tags, importance, expires_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    entry.id,
                    entry.type,
                    json.dumps(entry.content),
                    entry.timestamp,
                    entry.access_count,
                    entry.last_accessed,
                    json.dumps(entry.tags),
                    entry.importance,
                    entry.expires_at
                ))
            
            self.stats["total_entries"] += 1
            if entry.type == "skill":
                self.stats["skill_entries"] += 1
            elif entry.type == "execution":
                self.stats["execution_entries"] += 1
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to store memory entry: {e}")
            return False
    
    def retrieve_memory(self, entry_id: str) -> Optional[MemoryEntry]:
        """Retrieve a memory entry by ID."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("""
                    SELECT id, type, content, timestamp, access_count, last_accessed, tags, importance, expires_at
                    FROM memory_entries WHERE id = ?
                """, (entry_id,))
                
                row = cursor.fetchone()
                if row:
                    # Update access count and last accessed
                    conn.execute("""
                        UPDATE memory_entries 
                        SET access_count = access_count + 1, last_accessed = ?
                        WHERE id = ?
                    """, (time.time(), entry_id))
                    
                    return MemoryEntry(
                        id=row[0],
                        type=row[1],
                        content=json.loads(row[2]),
                        timestamp=row[3],
                        access_count=row[4] + 1,
                        last_accessed=time.time(),
                        tags=json.loads(row[5] or "[]"),
                        importance=row[6],
                        expires_at=row[7]
                    )
            
            self.stats["cache_misses"] += 1
            return None
            
        except Exception as e:
            logger.error(f"Failed to retrieve memory entry: {e}")
            self.stats["cache_misses"] += 1
            return None
    
    def search_memory(self, query: str, entry_type: str = None, limit: int = 10) -> List[MemoryEntry]:
        """Search memory entries by content query."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                sql = """
                    SELECT id, type, content, timestamp, access_count, last_accessed, tags, importance, expires_at
                    FROM memory_entries 
                    WHERE content LIKE ? 
                """
                params = [f"%{query}%"]
                
                if entry_type:
                    sql += " AND type = ?"
                    params.append(entry_type)
                
                sql += " ORDER BY importance DESC, timestamp DESC LIMIT ?"
                params.append(limit)
                
                cursor = conn.execute(sql, params)
                entries = []
                
                for row in cursor.fetchall():
                    entry = MemoryEntry(
                        id=row[0],
                        type=row[1],
                        content=json.loads(row[2]),
                        timestamp=row[3],
                        access_count=row[4],
                        last_accessed=row[5],
                        tags=json.loads(row[6] or "[]"),
                        importance=row[7],
                        expires_at=row[8]
                    )
                    entries.append(entry)
                
                return entries
                
        except Exception as e:
            logger.error(f"Memory search failed: {e}")
            return []
    
    def store_execution_memory(self, execution: ExecutionMemory) -> bool:
        """Store execution memory for learning."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO execution_memory 
                    (plan_id, command, plan_source, actions, success, execution_time, error_message, context, feedback_score, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    execution.plan_id,
                    execution.command,
                    execution.plan_source,
                    json.dumps(execution.actions),
                    execution.success,
                    execution.execution_time,
                    execution.error_message,
                    json.dumps(execution.context),
                    execution.feedback_score,
                    time.time()
                ))
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to store execution memory: {e}")
            return False
    
    def get_execution_history(self, command_pattern: str = None, limit: int = 20) -> List[ExecutionMemory]:
        """Get execution history, optionally filtered by command pattern."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                sql = """
                    SELECT plan_id, command, plan_source, actions, success, execution_time, 
                           error_message, context, feedback_score, timestamp
                    FROM execution_memory
                """
                params = []
                
                if command_pattern:
                    sql += " WHERE command LIKE ?"
                    params.append(f"%{command_pattern}%")
                
                sql += " ORDER BY timestamp DESC LIMIT ?"
                params.append(limit)
                
                cursor = conn.execute(sql, params)
                executions = []
                
                for row in cursor.fetchall():
                    execution = ExecutionMemory(
                        plan_id=row[0],
                        command=row[1],
                        plan_source=row[2],
                        actions=json.loads(row[3]),
                        success=bool(row[4]),
                        execution_time=row[5],
                        error_message=row[6],
                        context=json.loads(row[7] or "{}"),
                        feedback_score=row[8]
                    )
                    executions.append(execution)
                
                return executions
                
        except Exception as e:
            logger.error(f"Failed to get execution history: {e}")
            return []
    
    def _cleanup_expired_entries(self):
        """Remove expired entries from memory."""
        try:
            current_time = time.time()
            
            with sqlite3.connect(self.db_path) as conn:
                # Remove expired memory entries
                cursor = conn.execute("""
                    DELETE FROM memory_entries WHERE expires_at IS NOT NULL AND expires_at < ?
                """, (current_time,))
                
                expired_count = cursor.rowcount
                if expired_count > 0:
                    logger.info(f"Cleaned up {expired_count} expired memory entries")
                
        except Exception as e:
            logger.error(f"Failed to cleanup expired entries: {e}")
    
    def get_stats(self) -> Dict:
        """Get memory statistics."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                # Get entry counts by type
                cursor = conn.execute("""
                    SELECT type, COUNT(*) FROM memory_entries GROUP BY type
                """)
                type_counts = dict(cursor.fetchall())
                
                # Get execution stats
                cursor = conn.execute("""
                    SELECT COUNT(*), AVG(success) FROM execution_memory
                """)
                total_executions, avg_success = cursor.fetchone()
                
                return {
                    **self.stats,
                    "entry_types": type_counts,
                    "total_executions": total_executions or 0,
                    "average_success_rate": avg_success or 0.0,
                    "cache_hit_rate": self.stats["cache_hits"] / max(self.stats["cache_hits"] + self.stats["cache_misses"], 1)
                }
                
        except Exception as e:
            logger.error(f"Failed to get memory stats: {e}")
            return self.stats


class LearningSystem:
    """
    Learning system that improves from execution history and user feedback.
    Implements reinforcement learning and preference learning.
    """
    
    def __init__(self, persistent_memory: PersistentMemory):
        self.memory = persistent_memory
        self.learning_enabled = True
        self.feedback_weights = {}
        
        # Learning parameters
        self.success_threshold = 0.8
        self.importance_decay_rate = 0.95
        self.feedback_learning_rate = 0.1
    
    def learn_from_execution(self, execution: ExecutionMemory):
        """Learn from execution results."""
        if not self.learning_enabled:
            return
        
        try:
            # Store execution memory
            self.memory.store_execution_memory(execution)
            
            # Update strategy preferences based on success
            self._update_strategy_preferences(execution)
            
            # Update importance of related memory entries
            self._update_related_importance(execution)
            
            logger.info(f"Learned from execution: {execution.command} (success: {execution.success})")
            
        except Exception as e:
            logger.error(f"Learning from execution failed: {e}")
    
    def learn_from_feedback(self, plan_id: str, feedback_score: float):
        """Learn from user feedback."""
        if not self.learning_enabled:
            return
        
        try:
            # Update execution memory with feedback
            with sqlite3.connect(self.memory.db_path) as conn:
                conn.execute("""
                    UPDATE execution_memory SET feedback_score = ? WHERE plan_id = ?
                """, (feedback_score, plan_id))
            
            # Update strategy weights based on feedback
            self._update_feedback_weights(plan_id, feedback_score)
            
            logger.info(f"Learned from feedback: {plan_id} (score: {feedback_score})")
            
        except Exception as e:
            logger.error(f"Learning from feedback failed: {e}")
    
    def _update_strategy_preferences(self, execution: ExecutionMemory):
        """Update strategy preferences based on execution success."""
        strategy = execution.plan_source
        success = execution.success
        
        if strategy not in self.feedback_weights:
            self.feedback_weights[strategy] = 0.5
        
        # Adjust weight based on success
        if success:
            self.feedback_weights[strategy] = min(
                self.feedback_weights[strategy] + 0.1, 1.0
            )
        else:
            self.feedback_weights[strategy] = max(
                self.feedback_weights[strategy] - 0.05, 0.1
            )
    
    def _update_feedback_weights(self, plan_id: str, feedback_score: float):
        """Update feedback weights based on user feedback."""
        try:
            # Get execution details
            with sqlite3.connect(self.memory.db_path) as conn:
                cursor = conn.execute("""
                    SELECT plan_source FROM execution_memory WHERE plan_id = ?
                """, (plan_id,))
                row = cursor.fetchone()
                
                if row:
                    strategy = row[0]
                    
                    # Update strategy weight based on feedback
                    if strategy not in self.feedback_weights:
                        self.feedback_weights[strategy] = 0.5
                    
                    # Move weight towards feedback score
                    current_weight = self.feedback_weights[strategy]
                    new_weight = current_weight + self.feedback_learning_rate * (feedback_score - current_weight)
                    self.feedback_weights[strategy] = max(min(new_weight, 1.0), 0.1)
                    
        except Exception as e:
            logger.error(f"Failed to update feedback weights: {e}")
    
    def _update_related_importance(self, execution: ExecutionMemory):
        """Update importance of related memory entries."""
        try:
            # Find related memory entries
            related_entries = self.memory.search_memory(
                execution.command[:20],  # Search by command prefix
                limit=5
            )
            
            for entry in related_entries:
                # Increase importance if execution was successful
                if execution.success:
                    entry.importance = min(entry.importance * 1.1, 1.0)
                else:
                    entry.importance = max(entry.importance * 0.9, 0.1)
                
                # Update entry
                self.memory.store_memory(entry)
                
        except Exception as e:
            logger.error(f"Failed to update related importance: {e}")
    
    def get_strategy_recommendations(self, command: str) -> Dict[str, float]:
        """Get strategy recommendations based on learning."""
        # Get similar successful executions
        similar_executions = self.memory.get_execution_history(
            command_pattern=command[:20], limit=10
        )
        
        strategy_scores = {}
        for execution in similar_executions:
            if execution.success:
                strategy = execution.plan_source
                if strategy not in strategy_scores:
                    strategy_scores[strategy] = []
                
                score = 1.0
                if execution.feedback_score is not None:
                    score = execution.feedback_score
                
                strategy_scores[strategy].append(score)
        
        # Calculate average scores
        recommendations = {}
        for strategy, scores in strategy_scores.items():
            recommendations[strategy] = sum(scores) / len(scores)
        
        # Blend with learned weights
        for strategy, weight in self.feedback_weights.items():
            if strategy in recommendations:
                recommendations[strategy] = (recommendations[strategy] + weight) / 2
            else:
                recommendations[strategy] = weight * 0.5
        
        return recommendations
    
    def get_learning_stats(self) -> Dict:
        """Get learning system statistics."""
        return {
            "learning_enabled": self.learning_enabled,
            "strategy_weights": self.feedback_weights.copy(),
            "total_executions": len(self.memory.get_execution_history()),
            "success_rate": self._calculate_success_rate()
        }
    
    def _calculate_success_rate(self) -> float:
        """Calculate overall success rate from execution history."""
        executions = self.memory.get_execution_history(limit=100)
        if not executions:
            return 0.0
        
        successful = sum(1 for e in executions if e.success)
        return successful / len(executions)


class MemoryModule:
    """
    Main memory module orchestrating all memory and learning capabilities.
    Integrates persistent memory with learning system and skill cache.
    """
    
    def __init__(self, skill_cache, db_path: str = None):
        self.skill_cache = skill_cache
        self.persistent_memory = PersistentMemory(db_path)
        self.learning_system = LearningSystem(self.persistent_memory)
        
        # Memory management
        self.cleanup_interval = 3600  # 1 hour
        self.last_cleanup = time.time()
        
    def store_skill(self, command: str, actions: List[Dict], success: bool, 
                   importance: float = 0.5) -> str:
        """Store a skill in memory."""
        try:
            # Create skill memory entry
            skill_id = f"skill_{int(time.time())}_{hash(command) % 10000}"
            
            skill_content = {
                "command": command,
                "actions": actions,
                "success": success,
                "importance": importance
            }
            
            memory_entry = MemoryEntry(
                id=skill_id,
                type="skill",
                content=skill_content,
                timestamp=time.time(),
                importance=importance,
                tags=["skill", "command"]
            )
            
            # Store in persistent memory
            self.persistent_memory.store_memory(memory_entry)
            
            # Also store in skill cache for fast access
            if success:
                self._store_in_skill_cache(command, actions)
            
            return skill_id
            
        except Exception as e:
            logger.error(f"Failed to store skill: {e}")
            return ""
    
    def _store_in_skill_cache(self, command: str, actions: List[Dict]):
        """Store skill in the existing skill cache system."""
        try:
            # Convert actions to semantic steps
            from cecil_brain.skill_cache import SemanticStep, CachedSkill
            
            semantic_steps = []
            for action in actions:
                step = SemanticStep(
                    intent=action.get("type", ""),
                    target=action.get("target", ""),
                    text=action.get("text", ""),
                    key=action.get("key", ""),
                    app=action.get("app", "")
                )
                semantic_steps.append(step)
            
            # Create cached skill
            skill = CachedSkill(
                id=f"cache_{int(time.time())}",
                command=command,
                command_embedding=[],  # Will be populated by cache
                steps=semantic_steps,
                app_context="",
                success_count=1,
                failure_count=0,
                last_executed=time.time(),
                created_at=time.time()
            )
            
            self.skill_cache.store(skill)
            
        except Exception as e:
            logger.error(f"Failed to store in skill cache: {e}")
    
    def learn_from_execution(self, command: str, plan: Dict, success: bool, 
                           execution_time: float, error_message: str = None):
        """Learn from execution results."""
        try:
            # Create execution memory
            execution = ExecutionMemory(
                plan_id=plan.get("plan_id", f"plan_{int(time.time())}"),
                command=command,
                plan_source=plan.get("source", ""),
                actions=plan.get("actions", []),
                success=success,
                execution_time=execution_time,
                error_message=error_message,
                context=plan.get("context", {})
            )
            
            # Learn from execution
            self.learning_system.learn_from_execution(execution)
            
            # Store skill if successful
            if success:
                self.store_skill(command, plan.get("actions", []), True)
            
        except Exception as e:
            logger.error(f"Failed to learn from execution: {e}")
    
    def provide_feedback(self, plan_id: str, feedback_score: float):
        """Provide user feedback for learning."""
        self.learning_system.learn_from_feedback(plan_id, feedback_score)
    
    def get_similar_skills(self, command: str, limit: int = 5) -> List[Dict]:
        """Get similar skills from memory."""
        try:
            # Search memory for similar skills
            similar_entries = self.persistent_memory.search_memory(
                command, entry_type="skill", limit=limit
            )
            
            skills = []
            for entry in similar_entries:
                skill_data = entry.content
                skills.append({
                    "id": entry.id,
                    "command": skill_data.get("command", ""),
                    "actions": skill_data.get("actions", []),
                    "success": skill_data.get("success", False),
                    "importance": entry.importance,
                    "timestamp": entry.timestamp
                })
            
            return skills
            
        except Exception as e:
            logger.error(f"Failed to get similar skills: {e}")
            return []
    
    def get_strategy_recommendations(self, command: str) -> Dict[str, float]:
        """Get strategy recommendations for a command."""
        return self.learning_system.get_strategy_recommendations(command)
    
    def cleanup_memory(self):
        """Perform memory cleanup and maintenance."""
        current_time = time.time()
        
        if current_time - self.last_cleanup > self.cleanup_interval:
            self.persistent_memory._cleanup_expired_entries()
            self.last_cleanup = current_time
            logger.info("Memory cleanup completed")
    
    def get_comprehensive_stats(self) -> Dict:
        """Get comprehensive memory and learning statistics."""
        return {
            "persistent_memory_stats": self.persistent_memory.get_stats(),
            "learning_stats": self.learning_system.get_learning_stats(),
            "skill_cache_stats": {
                "cached_skills": self.skill_cache.count,
                "cache_available": self.skill_cache is not None
            }
        }
