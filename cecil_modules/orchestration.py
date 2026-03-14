"""
Modular Orchestration System - Phase 2.5

Central orchestration system that coordinates all modules.
Implements the modular architecture inspired by Simular S2.
"""

import logging
import time
import threading
from typing import Dict, List, Optional, Any, Callable
from enum import Enum
from dataclasses import dataclass

logger = logging.getLogger("cecil.orchestration")


class OrchestrationMode(Enum):
    """Orchestration mode enumeration."""
    AUTO = "auto"  # Automatic module selection
    MANUAL = "manual"  # Manual module specification
    HYBRID = "hybrid"  # Hybrid approach
    LEARNING = "learning"  # Learning-based selection


class TaskComplexity(Enum):
    """Task complexity levels."""
    SIMPLE = "simple"  # 1-3 actions
    MODERATE = "moderate"  # 4-8 actions
    COMPLEX = "complex"  # 9-15 actions
    VERY_COMPLEX = "very_complex"  # 16+ actions


@dataclass
class OrchestrationContext:
    """Context for orchestration decisions."""
    command: str
    user_preferences: Dict
    task_complexity: TaskComplexity
    available_modules: Dict[str, bool]
    performance_history: Dict[str, float]
    current_time: float
    
    @classmethod
    def create(cls, command: str, modules_status: Dict, history: Dict = None) -> "OrchestrationContext":
        """Create orchestration context from command and modules."""
        # Estimate task complexity
        complexity = cls._estimate_complexity(command)
        
        return cls(
            command=command,
            user_preferences={},  # Could be loaded from user profile
            task_complexity=complexity,
            available_modules=modules_status,
            performance_history=history or {},
            current_time=time.time()
        )
    
    @staticmethod
    def _estimate_complexity(command: str) -> TaskComplexity:
        """Estimate task complexity from command."""
        command_lower = command.lower()
        
        # Simple indicators
        simple_keywords = ["abre", "cierra", "minimiza", "maximiza", "click", "presiona"]
        moderate_keywords = ["busca", "escribe", "navega", "selecciona", "copia", "pega"]
        complex_keywords = ["organiza", "analiza", "procesa", "genera", "exporta", "importa"]
        very_complex_keywords = ["automatiza", "integra", "sincroniza", "transforma", "migra"]
        
        for keyword in very_complex_keywords:
            if keyword in command_lower:
                return TaskComplexity.VERY_COMPLEX
        
        for keyword in complex_keywords:
            if keyword in command_lower:
                return TaskComplexity.COMPLEX
        
        for keyword in moderate_keywords:
            if keyword in command_lower:
                return TaskComplexity.MODERATE
        
        return TaskComplexity.SIMPLE


class ModuleSelector:
    """
    Intelligent module selection based on context and performance.
    Implements the modular approach from Simular S2.
    """
    
    def __init__(self):
        self.selection_weights = {
            "perception": {"coordinate_free": 0.7, "traditional": 0.3},
            "planning": {"hybrid": 0.4, "openclaw_enhanced": 0.3, "llm": 0.2, "cache_first": 0.1},
            "execution": {"coordinate_free": 0.6, "coordinate_based": 0.4},
            "memory": {"persistent": 0.8, "cache_only": 0.2}
        }
        
        self.performance_history = {}
        self.selection_stats = {
            "total_selections": 0,
            "successful_selections": 0,
            "module_usage": {}
        }
    
    def select_modules(self, context: OrchestrationContext) -> Dict[str, str]:
        """
        Select optimal modules for the given context.
        Returns module configuration.
        """
        self.selection_stats["total_selections"] += 1
        
        try:
            # Base selection on task complexity
            if context.task_complexity == TaskComplexity.SIMPLE:
                return self._select_for_simple_task(context)
            elif context.task_complexity == TaskComplexity.MODERATE:
                return self._select_for_moderate_task(context)
            elif context.task_complexity == TaskComplexity.COMPLEX:
                return self._select_for_complex_task(context)
            else:  # VERY_COMPLEX
                return self._select_for_very_complex_task(context)
                
        except Exception as e:
            logger.error(f"Module selection failed: {e}")
            return self._get_fallback_configuration()
    
    def _select_for_simple_task(self, context: OrchestrationContext) -> Dict[str, str]:
        """Select modules for simple tasks."""
        return {
            "perception": "traditional",  # Fast and simple
            "planning": "cache_first",    # Prefer cached solutions
            "execution": "coordinate_based",  # Direct execution
            "memory": "cache_only"        # Fast access
        }
    
    def _select_for_moderate_task(self, context: OrchestrationContext) -> Dict[str, str]:
        """Select modules for moderate tasks."""
        return {
            "perception": "coordinate_free",  # Better accuracy
            "planning": "hybrid",            # Balanced approach
            "execution": "coordinate_free",   # Semantic execution
            "memory": "persistent"           # Store for learning
        }
    
    def _select_for_complex_task(self, context: OrchestrationContext) -> Dict[str, str]:
        """Select modules for complex tasks."""
        return {
            "perception": "coordinate_free",  # Best accuracy
            "planning": "openclaw_enhanced", # Powerful planning
            "execution": "coordinate_free",   # Robust execution
            "memory": "persistent"           # Full learning
        }
    
    def _select_for_very_complex_task(self, context: OrchestrationContext) -> Dict[str, str]:
        """Select modules for very complex tasks."""
        return {
            "perception": "coordinate_free",  # Maximum accuracy
            "planning": "hybrid",            # Best of all approaches
            "execution": "coordinate_free",   # Most robust
            "memory": "persistent"           # Full learning
        }
    
    def _get_fallback_configuration(self) -> Dict[str, str]:
        """Get fallback module configuration."""
        return {
            "perception": "traditional",
            "planning": "cache_first",
            "execution": "coordinate_based",
            "memory": "cache_only"
        }
    
    def update_performance(self, module_config: Dict[str, str], success: bool, 
                          execution_time: float):
        """Update performance history for learning."""
        config_key = self._config_to_key(module_config)
        
        if config_key not in self.performance_history:
            self.performance_history[config_key] = {
                "success_count": 0,
                "total_count": 0,
                "total_time": 0.0,
                "avg_time": 0.0,
                "success_rate": 0.0
            }
        
        perf = self.performance_history[config_key]
        perf["total_count"] += 1
        perf["total_time"] += execution_time
        
        if success:
            perf["success_count"] += 1
            self.selection_stats["successful_selections"] += 1
        
        perf["avg_time"] = perf["total_time"] / perf["total_count"]
        perf["success_rate"] = perf["success_count"] / perf["total_count"]
        
        # Update module usage stats
        for module_type, module_choice in module_config.items():
            if module_type not in self.selection_stats["module_usage"]:
                self.selection_stats["module_usage"][module_type] = {}
            
            if module_choice not in self.selection_stats["module_usage"][module_type]:
                self.selection_stats["module_usage"][module_type][module_choice] = 0
            
            self.selection_stats["module_usage"][module_type][module_choice] += 1
    
    def _config_to_key(self, config: Dict[str, str]) -> str:
        """Convert module configuration to string key."""
        return "_".join([f"{k}:{v}" for k, v in sorted(config.items())])
    
    def get_selection_stats(self) -> Dict:
        """Get module selection statistics."""
        total = self.selection_stats["total_selections"]
        if total == 0:
            return self.selection_stats
        
        return {
            **self.selection_stats,
            "success_rate": self.selection_stats["successful_selections"] / total
        }


class ModularOrchestrator:
    """
    Main orchestrator that coordinates all modules in the modular architecture.
    Implements the Simular S2 inspired modular approach.
    """
    
    def __init__(self, perception_module, planning_module, execution_module, memory_module):
        self.perception = perception_module
        self.planning = planning_module
        self.execution = execution_module
        self.memory = memory_module
        
        self.module_selector = ModuleSelector()
        self.orchestration_mode = OrchestrationMode.AUTO
        self.current_task = None
        self.task_history = []
        
        # Performance tracking
        self.orchestration_stats = {
            "total_tasks": 0,
            "successful_tasks": 0,
            "failed_tasks": 0,
            "avg_task_time": 0.0,
            "module_switches": 0
        }
        
        # Thread safety
        self.execution_lock = threading.Lock()
        self.cancel_flag = threading.Event()
    
    def execute_command(self, command: str, user_context: Dict = None) -> Dict:
        """
        Execute a command using the modular orchestration system.
        """
        start_time = time.time()
        self.orchestration_stats["total_tasks"] += 1
        
        try:
            # Create orchestration context
            modules_status = self._get_modules_status()
            context = OrchestrationContext.create(command, modules_status)
            
            # Select modules
            module_config = self.module_selector.select_modules(context)
            
            # Execute using selected modules
            result = self._execute_with_modules(command, module_config, user_context)
            
            # Update performance
            execution_time = time.time() - start_time
            success = result.get("success", False)
            
            self.module_selector.update_performance(module_config, success, execution_time)
            self._update_orchestration_stats(success, execution_time)
            
            # Store in memory for learning
            self.memory.learn_from_execution(command, result.get("plan", {}), 
                                           success, execution_time)
            
            # Add to task history
            self.task_history.append({
                "command": command,
                "module_config": module_config,
                "success": success,
                "execution_time": execution_time,
                "timestamp": time.time()
            })
            
            return result
            
        except Exception as e:
            self.orchestration_stats["failed_tasks"] += 1
            logger.error(f"Orchestration failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "execution_time": time.time() - start_time
            }
    
    def _execute_with_modules(self, command: str, module_config: Dict[str, str], 
                            user_context: Dict = None) -> Dict:
        """Execute command using specified module configuration."""
        try:
            # Step 1: Perception
            perception_result = self._execute_perception(command, module_config["perception"])
            
            # Step 2: Planning
            planning_context = {
                "active_app": self._get_active_app(),
                "keybindings": self._get_keybindings(),
                "screenshot_path": perception_result.get("screenshot_path"),
                "perception_data": perception_result
            }
            
            planning_result = self._execute_planning(command, module_config["planning"], planning_context)
            
            if not planning_result.get("ready_for_execution", False):
                return {
                    "success": False,
                    "error": "Planning validation failed",
                    "planning_result": planning_result
                }
            
            # Step 3: Execution
            execution_result = self._execute_execution(
                planning_result["plan"], module_config["execution"], command
            )
            
            # Step 4: Memory consolidation
            self._execute_memory(module_config["memory"], command, planning_result, execution_result)
            
            return {
                "success": execution_result.get("success", False),
                "command": command,
                "module_config": module_config,
                "perception_result": perception_result,
                "planning_result": planning_result,
                "execution_result": execution_result,
                "execution_time": execution_result.get("execution_time", 0)
            }
            
        except Exception as e:
            logger.error(f"Module execution failed: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def _execute_perception(self, command: str, perception_type: str) -> Dict:
        """Execute perception using specified approach."""
        try:
            use_coordinate_free = perception_type == "coordinate_free"
            
            parse_result = self.perception.parse_screen(
                use_coordinate_free=use_coordinate_free
            )
            
            if "error" in parse_result:
                return {"success": False, "error": parse_result["error"]}
            
            return {
                "success": True,
                "perception_type": perception_type,
                "parse_result": parse_result,
                "screenshot_path": parse_result.get("screenshot_path")
            }
            
        except Exception as e:
            return {"success": False, "error": f"Perception failed: {e}"}
    
    def _execute_planning(self, command: str, planning_type: str, context: Dict) -> Dict:
        """Execute planning using specified approach."""
        try:
            from cecil_modules.planning import PlanningStrategy
            
            strategy_map = {
                "cache_first": PlanningStrategy.CACHE_FIRST,
                "openclaw_enhanced": PlanningStrategy.OPENCLAW_ENHANCED,
                "llm": PlanningStrategy.LLM_PLANNING,
                "hybrid": PlanningStrategy.HYBRID
            }
            
            strategy = strategy_map.get(planning_type, PlanningStrategy.HYBRID)
            
            result = self.planning.plan_and_validate(command, context, strategy)
            
            return result
            
        except Exception as e:
            return {
                "ready_for_execution": False,
                "error": f"Planning failed: {e}"
            }
    
    def _execute_execution(self, plan: Dict, execution_type: str, command: str) -> Dict:
        """Execute plan using specified approach."""
        try:
            # For now, execution type doesn't change the execution method
            # In a full implementation, this would affect coordinate resolution
            result = self.execution.execute_plan(plan, command)
            
            return result
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Execution failed: {e}"
            }
    
    def _execute_memory(self, memory_type: str, command: str, planning_result: Dict, 
                       execution_result: Dict):
        """Execute memory consolidation."""
        try:
            if memory_type == "persistent":
                # Full memory consolidation
                pass  # Already handled in main execution flow
            elif memory_type == "cache_only":
                # Cache-only approach
                pass  # Already handled in main execution flow
            
        except Exception as e:
            logger.error(f"Memory consolidation failed: {e}")
    
    def _get_modules_status(self) -> Dict[str, bool]:
        """Get status of all modules."""
        return {
            "perception": True,  # Always available
            "planning": True,   # Always available
            "execution": True,  # Always available
            "memory": True      # Always available
        }
    
    def _get_active_app(self) -> str:
        """Get currently active application."""
        try:
            if hasattr(self.execution, 'action_executor'):
                if hasattr(self.execution.action_executor, 'input_executor'):
                    active_win = self.execution.action_executor.input_executor.get_active_window()
                    return active_win.get("class", "").lower()
        except:
            pass
        return ""
    
    def _get_keybindings(self) -> str:
        """Get current keybindings context."""
        try:
            from cecil_brain.keybindings import keybindings_to_context
            return keybindings_to_context(self._get_active_app(), include_hyprland=True)
        except:
            return ""
    
    def _update_orchestration_stats(self, success: bool, execution_time: float):
        """Update orchestration statistics."""
        if success:
            self.orchestration_stats["successful_tasks"] += 1
        else:
            self.orchestration_stats["failed_tasks"] += 1
        
        # Update average time
        total = self.orchestration_stats["total_tasks"]
        current_avg = self.orchestration_stats["avg_task_time"]
        self.orchestration_stats["avg_task_time"] = (
            (current_avg * (total - 1) + execution_time) / total
        )
    
    def cancel_current_task(self):
        """Cancel current task execution."""
        self.cancel_flag.set()
        self.execution.cancel_execution()
        logger.info("Task cancellation requested")
    
    def reset_cancel_flag(self):
        """Reset cancellation flag."""
        self.cancel_flag.clear()
    
    def get_task_history(self, limit: int = 20) -> List[Dict]:
        """Get recent task history."""
        return self.task_history[-limit:]
    
    def get_comprehensive_stats(self) -> Dict:
        """Get comprehensive orchestration statistics."""
        return {
            "orchestration_stats": self.orchestration_stats,
            "module_selector_stats": self.module_selector.get_selection_stats(),
            "module_stats": {
                "perception": self.perception.get_stats(),
                "planning": self.planning.get_stats(),
                "execution": self.execution.get_stats(),
                "memory": self.memory.get_comprehensive_stats()
            }
        }
    
    def set_orchestration_mode(self, mode: OrchestrationMode):
        """Set orchestration mode."""
        self.orchestration_mode = mode
        logger.info(f"Orchestration mode set to: {mode.value}")


class OrchestrationModule:
    """
    Main orchestration module providing the interface for the modular system.
    This is the entry point for the Phase 2 modular architecture.
    """
    
    def __init__(self, perception_module, planning_module, execution_module, memory_module):
        self.orchestrator = ModularOrchestrator(
            perception_module, planning_module, execution_module, memory_module
        )
        
        # Module references for direct access
        self.perception = perception_module
        self.planning = planning_module
        self.execution = execution_module
        self.memory = memory_module
    
    def execute_command(self, command: str, user_context: Dict = None) -> Dict:
        """Execute a command using the modular orchestration system."""
        return self.orchestrator.execute_command(command, user_context)
    
    def execute_command_async(self, command: str, user_context: Dict = None, 
                             callback: Callable = None) -> threading.Thread:
        """Execute command asynchronously."""
        def async_execution():
            result = self.execute_command(command, user_context)
            if callback:
                callback(result)
        
        thread = threading.Thread(target=async_execution, daemon=True)
        thread.start()
        return thread
    
    def cancel_execution(self):
        """Cancel current execution."""
        self.orchestrator.cancel_current_task()
    
    def get_stats(self) -> Dict:
        """Get comprehensive system statistics."""
        return self.orchestrator.get_comprehensive_stats()
    
    def get_task_history(self, limit: int = 20) -> List[Dict]:
        """Get recent task history."""
        return self.orchestrator.get_task_history(limit)
    
    def provide_feedback(self, task_id: str, feedback_score: float):
        """Provide feedback for learning."""
        self.memory.provide_feedback(task_id, feedback_score)
    
    def cleanup(self):
        """Perform system cleanup."""
        self.memory.cleanup_memory()
        logger.info("Orchestration cleanup completed")
