"""
Execution Module - Phase 2.3

Implements modular execution with OpenClaw tools, ydotool integration, and action coordination.
Handles both coordinate-based and coordinate-free actions.
"""

import logging
import time
from typing import Dict, List, Optional, Any, Callable
from enum import Enum
import threading
from dataclasses import dataclass

logger = logging.getLogger("cecil.execution")


class ActionType(Enum):
    """Action type enumeration."""
    TAP = "tap"
    DOUBLE_CLICK = "double_click"
    RIGHT_CLICK = "right_click"
    TYPE = "type"
    KEY = "key"
    SCROLL = "scroll"
    WAIT = "wait"
    LAUNCH_APP = "launch_app"
    CLOSE_WINDOW = "close_window"
    HOVER = "hover"
    FOCUS_WINDOW = "focus_window"


class ExecutionStatus(Enum):
    """Execution status enumeration."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class ExecutionContext:
    """Context for action execution."""
    command: str
    plan_id: str
    screenshot_before: Optional[str] = None
    screenshot_after: Optional[str] = None
    execution_time: float = 0.0
    error_message: Optional[str] = None


class ActionExecutor:
    """
    Base action executor with support for multiple execution backends.
    Handles both coordinate-based and coordinate-free actions.
    """
    
    def __init__(self, input_executor, mcp_bridge=None):
        self.input_executor = input_executor
        self.mcp_bridge = mcp_bridge
        self.execution_stats = {
            "total_actions": 0,
            "successful_actions": 0,
            "failed_actions": 0,
            "coordinate_free_actions": 0,
            "coordinate_based_actions": 0,
            "mcp_actions": 0
        }
        
    def execute_action(self, action: Dict, context: ExecutionContext = None) -> Dict:
        """
        Execute a single action with proper error handling and logging.
        """
        start_time = time.time()
        self.execution_stats["total_actions"] += 1
        
        try:
            action_type = action.get("type", action.get("action", ""))
            
            # Normalize action type
            if action_type == "action":
                action_type = action.get("action", "")
            
            # Check if this is a coordinate-free action
            is_coordinate_free = self._is_coordinate_free_action(action)
            
            if is_coordinate_free:
                self.execution_stats["coordinate_free_actions"] += 1
                result = self._execute_coordinate_free_action(action, context)
            else:
                self.execution_stats["coordinate_based_actions"] += 1
                result = self._execute_coordinate_based_action(action, context)
            
            # Record execution time
            execution_time = time.time() - start_time
            result["execution_time"] = execution_time
            result["coordinate_free"] = is_coordinate_free
            
            # Update stats
            if result.get("success", False):
                self.execution_stats["successful_actions"] += 1
            else:
                self.execution_stats["failed_actions"] += 1
            
            return result
            
        except Exception as e:
            self.execution_stats["failed_actions"] += 1
            return {
                "success": False,
                "error": str(e),
                "execution_time": time.time() - start_time,
                "coordinate_free": False
            }
    
    def _is_coordinate_free_action(self, action: Dict) -> bool:
        """Determine if action is coordinate-free."""
        # Check for semantic targets instead of coordinates
        has_semantic_target = (
            "target" in action and 
            isinstance(action["target"], str) and 
            len(action["target"]) > 0
        )
        
        # Check for lack of explicit coordinates
        has_coordinates = ("x" in action and "y" in action)
        
        return has_semantic_target and not has_coordinates
    
    def _execute_coordinate_free_action(self, action: Dict, context: ExecutionContext = None) -> Dict:
        """
        Execute coordinate-free action using semantic targets.
        Requires resolution of semantic targets to actual coordinates.
        """
        try:
            target = action.get("target", "")
            action_type = action.get("type", "")
            
            # Resolve semantic target to coordinates
            coordinates = self._resolve_semantic_target(target, context)
            
            if not coordinates:
                return {
                    "success": False,
                    "error": f"Could not resolve semantic target: {target}"
                }
            
            # Create coordinate-based action from resolved coordinates
            resolved_action = action.copy()
            resolved_action.update(coordinates)
            resolved_action["type"] = action_type
            
            # Execute resolved action
            return self._execute_coordinate_based_action(resolved_action, context)
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Coordinate-free execution failed: {e}"
            }
    
    def _resolve_semantic_target(self, target: str, context: ExecutionContext = None) -> Optional[Dict]:
        """
        Resolve semantic target to actual coordinates.
        Uses perception module data if available.
        """
        try:
            # This would integrate with the perception module
            # For now, return None to indicate resolution failure
            # In a full implementation, this would:
            # 1. Query the perception module for semantic regions
            # 2. Find the region matching the target
            # 3. Extract coordinates from the region
            
            logger.warning(f"Semantic target resolution not implemented: {target}")
            return None
            
        except Exception as e:
            logger.error(f"Semantic target resolution failed: {e}")
            return None
    
    def _execute_coordinate_based_action(self, action: Dict, context: ExecutionContext = None) -> Dict:
        """
        Execute coordinate-based action using input executor.
        """
        try:
            action_type = action.get("type", "")
            
            if action_type == ActionType.TAP.value:
                return self._execute_tap(action)
            elif action_type == ActionType.DOUBLE_CLICK.value:
                return self._execute_double_click(action)
            elif action_type == ActionType.RIGHT_CLICK.value:
                return self._execute_right_click(action)
            elif action_type == ActionType.TYPE.value:
                return self._execute_type(action)
            elif action_type == ActionType.KEY.value:
                return self._execute_key(action)
            elif action_type == ActionType.SCROLL.value:
                return self._execute_scroll(action)
            elif action_type == ActionType.WAIT.value:
                return self._execute_wait(action)
            elif action_type == ActionType.LAUNCH_APP.value:
                return self._execute_launch_app(action)
            elif action_type == ActionType.CLOSE_WINDOW.value:
                return self._execute_close_window(action)
            elif action_type == ActionType.HOVER.value:
                return self._execute_hover(action)
            elif action_type == ActionType.FOCUS_WINDOW.value:
                return self._execute_focus_window(action)
            else:
                return {
                    "success": False,
                    "error": f"Unknown action type: {action_type}"
                }
                
        except Exception as e:
            return {
                "success": False,
                "error": f"Action execution failed: {e}"
            }
    
    def _execute_tap(self, action: Dict) -> Dict:
        """Execute tap/click action."""
        x = action.get("x")
        y = action.get("y")
        
        if x is None or y is None:
            return {"success": False, "error": "Missing coordinates for tap action"}
        
        success = self.input_executor.tap(x, y)
        return {"success": success, "action": "tap", "coordinates": (x, y)}
    
    def _execute_double_click(self, action: Dict) -> Dict:
        """Execute double click action."""
        x = action.get("x")
        y = action.get("y")
        
        if x is None or y is None:
            return {"success": False, "error": "Missing coordinates for double click"}
        
        success = self.input_executor.double_click(x, y)
        return {"success": success, "action": "double_click", "coordinates": (x, y)}
    
    def _execute_right_click(self, action: Dict) -> Dict:
        """Execute right click action."""
        x = action.get("x")
        y = action.get("y")
        
        if x is None or y is None:
            return {"success": False, "error": "Missing coordinates for right click"}
        
        success = self.input_executor.right_click(x, y)
        return {"success": success, "action": "right_click", "coordinates": (x, y)}
    
    def _execute_type(self, action: Dict) -> Dict:
        """Execute type action."""
        text = action.get("text", "")
        
        if not text:
            return {"success": False, "error": "Missing text for type action"}
        
        success = self.input_executor.type_text(text)
        return {"success": success, "action": "type", "text": text}
    
    def _execute_key(self, action: Dict) -> Dict:
        """Execute key press action."""
        key_combo = action.get("key", "")
        
        if not key_combo:
            return {"success": False, "error": "Missing key combination"}
        
        success = self.input_executor.press_keys(key_combo)
        return {"success": success, "action": "key", "key_combo": key_combo}
    
    def _execute_scroll(self, action: Dict) -> Dict:
        """Execute scroll action."""
        x = action.get("x", 0)
        y = action.get("y", 0)
        direction = action.get("direction", "down")
        clicks = action.get("clicks", 1)
        
        success = self.input_executor.scroll(x, y, direction, clicks)
        return {
            "success": success, 
            "action": "scroll", 
            "coordinates": (x, y),
            "direction": direction,
            "clicks": clicks
        }
    
    def _execute_wait(self, action: Dict) -> Dict:
        """Execute wait action."""
        duration = action.get("duration", 1.0)
        
        time.sleep(duration)
        return {"success": True, "action": "wait", "duration": duration}
    
    def _execute_launch_app(self, action: Dict) -> Dict:
        """Execute launch app action."""
        app = action.get("app", "")
        
        if not app:
            return {"success": False, "error": "Missing app name"}
        
        success = self.input_executor.launch_app(app)
        return {"success": success, "action": "launch_app", "app": app}
    
    def _execute_close_window(self, action: Dict) -> Dict:
        """Execute close window action."""
        success = self.input_executor.close_window()
        return {"success": success, "action": "close_window"}
    
    def _execute_hover(self, action: Dict) -> Dict:
        """Execute hover action."""
        x = action.get("x")
        y = action.get("y")
        
        if x is None or y is None:
            return {"success": False, "error": "Missing coordinates for hover"}
        
        success = self.input_executor.hover(x, y)
        return {"success": success, "action": "hover", "coordinates": (x, y)}
    
    def _execute_focus_window(self, action: Dict) -> Dict:
        """Execute focus window action."""
        window_class = action.get("window_class", "")
        
        if not window_class:
            return {"success": False, "error": "Missing window class"}
        
        success = self.input_executor.focus_window(window_class)
        return {"success": success, "action": "focus_window", "window_class": window_class}
    
    def get_stats(self) -> Dict:
        """Get execution statistics."""
        total = self.execution_stats["total_actions"]
        if total == 0:
            return self.execution_stats
        
        return {
            **self.execution_stats,
            "success_rate": self.execution_stats["successful_actions"] / total,
            "failure_rate": self.execution_stats["failed_actions"] / total,
            "coordinate_free_rate": self.execution_stats["coordinate_free_actions"] / total
        }


class ExecutionOrchestrator:
    """
    Orchestrates the execution of action plans with proper sequencing and error handling.
    Supports both synchronous and asynchronous execution.
    """
    
    def __init__(self, action_executor, perception_module=None):
        self.action_executor = action_executor
        self.perception_module = perception_module
        self.execution_history = []
        self.current_execution = None
        self.cancel_flag = threading.Event()
        
    def execute_plan(self, plan: Dict, context: ExecutionContext = None) -> Dict:
        """
        Execute a complete action plan.
        """
        if context is None:
            context = ExecutionContext(
                command="",
                plan_id=f"plan_{int(time.time())}"
            )
        
        self.current_execution = {
            "context": context,
            "plan": plan,
            "start_time": time.time(),
            "status": ExecutionStatus.RUNNING,
            "results": []
        }
        
        try:
            actions = plan.get("actions", [])
            total_actions = len(actions)
            
            logger.info(f"Executing plan with {total_actions} actions")
            
            for i, action in enumerate(actions):
                # Check for cancellation
                if self.cancel_flag.is_set():
                    self.current_execution["status"] = ExecutionStatus.CANCELLED
                    break
                
                # Execute action
                result = self.action_executor.execute_action(action, context)
                result["action_index"] = i
                result["total_actions"] = total_actions
                
                # Store result
                self.current_execution["results"].append(result)
                
                # Check for failure
                if not result.get("success", False):
                    logger.error(f"Action {i} failed: {result.get('error')}")
                    # Continue execution for now, but could implement retry logic
                
                # Small delay between actions
                time.sleep(0.1)
            
            # Finalize execution
            self.current_execution["end_time"] = time.time()
            self.current_execution["execution_time"] = (
                self.current_execution["end_time"] - self.current_execution["start_time"]
            )
            
            # Determine overall success
            successful_actions = sum(1 for r in self.current_execution["results"] if r.get("success", False))
            self.current_execution["success_rate"] = successful_actions / total_actions
            
            if self.cancel_flag.is_set():
                self.current_execution["status"] = ExecutionStatus.CANCELLED
            elif self.current_execution["success_rate"] >= 0.8:
                self.current_execution["status"] = ExecutionStatus.COMPLETED
            else:
                self.current_execution["status"] = ExecutionStatus.FAILED
            
            # Store in history
            self.execution_history.append(self.current_execution)
            
            return self._create_execution_summary()
            
        except Exception as e:
            self.current_execution["status"] = ExecutionStatus.FAILED
            self.current_execution["error"] = str(e)
            self.current_execution["end_time"] = time.time()
            
            return {
                "success": False,
                "error": str(e),
                "execution_time": time.time() - self.current_execution["start_time"]
            }
    
    def execute_plan_async(self, plan: Dict, context: ExecutionContext = None, 
                          callback: Callable = None):
        """
        Execute plan asynchronously.
        """
        def async_execution():
            result = self.execute_plan(plan, context)
            if callback:
                callback(result)
        
        thread = threading.Thread(target=async_execution, daemon=True)
        thread.start()
        return thread
    
    def cancel_execution(self):
        """Cancel current execution."""
        self.cancel_flag.set()
        logger.info("Execution cancellation requested")
    
    def reset_cancel_flag(self):
        """Reset cancellation flag for new execution."""
        self.cancel_flag.clear()
    
    def _create_execution_summary(self) -> Dict:
        """Create execution summary from current execution."""
        if not self.current_execution:
            return {"error": "No execution data available"}
        
        results = self.current_execution["results"]
        successful_actions = sum(1 for r in results if r.get("success", False))
        total_actions = len(results)
        
        return {
            "success": self.current_execution["status"] == ExecutionStatus.COMPLETED,
            "status": self.current_execution["status"].value,
            "total_actions": total_actions,
            "successful_actions": successful_actions,
            "failed_actions": total_actions - successful_actions,
            "success_rate": successful_actions / total_actions if total_actions > 0 else 0,
            "execution_time": self.current_execution.get("execution_time", 0),
            "plan_id": self.current_execution["context"].plan_id,
            "results": results
        }
    
    def get_execution_history(self, limit: int = 10) -> List[Dict]:
        """Get recent execution history."""
        return self.execution_history[-limit:]
    
    def get_stats(self) -> Dict:
        """Get execution statistics."""
        executor_stats = self.action_executor.get_stats()
        
        # Add orchestrator-specific stats
        total_executions = len(self.execution_history)
        if total_executions == 0:
            return executor_stats
        
        successful_executions = sum(
            1 for exec_data in self.execution_history 
            if exec_data.get("status") == ExecutionStatus.COMPLETED
        )
        
        return {
            **executor_stats,
            "total_executions": total_executions,
            "successful_executions": successful_executions,
            "execution_success_rate": successful_executions / total_executions
        }


class ExecutionModule:
    """
    Main execution module orchestrating all execution capabilities.
    Integrates action executor with orchestrator and MCP tools.
    """
    
    def __init__(self, input_executor, mcp_bridge=None, perception_module=None):
        self.action_executor = ActionExecutor(input_executor, mcp_bridge)
        self.orchestrator = ExecutionOrchestrator(self.action_executor, perception_module)
        self.mcp_bridge = mcp_bridge
        
    def execute_plan(self, plan: Dict, command: str = "", screenshot_before: str = None) -> Dict:
        """
        Execute a plan with full context tracking.
        """
        context = ExecutionContext(
            command=command,
            plan_id=f"plan_{int(time.time())}",
            screenshot_before=screenshot_before
        )
        
        result = self.orchestrator.execute_plan(plan, context)
        
        # Add screenshot after execution if available
        if self.orchestrator.perception_module:
            try:
                context.screenshot_after = self.orchestrator.perception_module.screen_capture.capture()
            except:
                pass
        
        return result
    
    def execute_plan_async(self, plan: Dict, command: str = "", 
                          screenshot_before: str = None, callback: Callable = None) -> threading.Thread:
        """Execute plan asynchronously."""
        context = ExecutionContext(
            command=command,
            plan_id=f"plan_{int(time.time())}",
            screenshot_before=screenshot_before
        )
        
        return self.orchestrator.execute_plan_async(plan, context, callback)
    
    def cancel_execution(self):
        """Cancel current execution."""
        self.orchestrator.cancel_execution()
    
    def get_stats(self) -> Dict:
        """Get comprehensive execution statistics."""
        return {
            "executor_stats": self.action_executor.get_stats(),
            "orchestrator_stats": self.orchestrator.get_stats()
        }
