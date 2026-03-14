"""
OSWorld Integration Module - Phase 3.1

Integrates CecilOs with OSWorld benchmark for competition evaluation.
Implements OSWorld agent interface with CecilOs modular architecture.
"""

import logging
import time
import json
import os
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
import numpy as np

logger = logging.getLogger("cecil.osworld")


@dataclass
class OSWorldTask:
    """OSWorld task representation."""
    task_id: str
    instruction: str
    category: str
    difficulty: str
    expected_actions: List[str]
    evaluation_criteria: Dict[str, Any]
    environment_setup: Dict[str, Any]


@dataclass
class OSWorldResult:
    """OSWorld evaluation result."""
    task_id: str
    success: bool
    accuracy: float
    efficiency: float
    safety: float
    reasoning_quality: float
    execution_time: float
    actions_taken: List[Dict]
    errors: List[str]
    metadata: Dict[str, Any]


class OSWorldAgent:
    """
    CecilOs agent implementation for OSWorld benchmark.
    Bridges CecilOs modular architecture with OSWorld evaluation framework.
    """
    
    def __init__(self, orchestration_module, perception_module, planning_module, execution_module, memory_module):
        self.orchestration = orchestration_module
        self.perception = perception_module
        self.planning = planning_module
        self.execution = execution_module
        self.memory = memory_module
        
        # OSWorld-specific configuration
        self.max_steps = 50  # OSWorld allows up to 50 steps
        self.max_time = 300  # 5 minutes per task
        self.safety_checks = True
        
        # Performance tracking
        self.evaluation_stats = {
            "total_tasks": 0,
            "successful_tasks": 0,
            "accuracy_scores": [],
            "efficiency_scores": [],
            "safety_scores": [],
            "reasoning_scores": [],
            "avg_execution_time": 0.0
        }
    
    def setup_environment(self, task: OSWorldTask) -> bool:
        """
        Setup environment for OSWorld task.
        This would configure the VM/desktop environment according to task requirements.
        """
        try:
            logger.info(f"Setting up environment for task {task.task_id}: {task.instruction}")
            
            # In a full implementation, this would:
            # 1. Parse task environment setup requirements
            # 2. Configure VM/desktop environment
            # 3. Install required applications
            # 4. Set up initial state
            
            # For now, assume environment is already set up
            return True
            
        except Exception as e:
            logger.error(f"Environment setup failed: {e}")
            return False
    
    def execute_task(self, task: OSWorldTask) -> OSWorldResult:
        """
        Execute an OSWorld task using CecilOs modular architecture.
        """
        start_time = time.time()
        self.evaluation_stats["total_tasks"] += 1
        
        try:
            logger.info(f"Executing OSWorld task {task.task_id}")
            
            # Setup environment
            if not self.setup_environment(task):
                return OSWorldResult(
                    task_id=task.task_id,
                    success=False,
                    accuracy=0.0,
                    efficiency=0.0,
                    safety=0.0,
                    reasoning_quality=0.0,
                    execution_time=time.time() - start_time,
                    actions_taken=[],
                    errors=["Environment setup failed"],
                    metadata={"error": "setup_failed"}
                )
            
            # Parse task instruction
            instruction = task.instruction
            
            # Step 1: Perception - Analyze current screen state
            perception_result = self._analyze_screen_state()
            
            # Step 2: Planning - Generate plan using modular architecture
            planning_context = self._create_planning_context(task, perception_result)
            plan_result = self.orchestration.execute_command(instruction, planning_context)
            
            if not plan_result.get("success", False):
                return OSWorldResult(
                    task_id=task.task_id,
                    success=False,
                    accuracy=0.0,
                    efficiency=0.0,
                    safety=0.0,
                    reasoning_quality=0.0,
                    execution_time=time.time() - start_time,
                    actions_taken=[],
                    errors=[plan_result.get("error", "Planning failed")],
                    metadata={"error": "planning_failed"}
                )
            
            # Step 3: Execution - Execute the plan with safety checks
            execution_result = self._execute_plan_with_safety(
                plan_result, task, start_time
            )
            
            # Step 4: Evaluation - Assess task completion
            evaluation_result = self._evaluate_task_completion(
                task, execution_result, perception_result
            )
            
            # Calculate final metrics
            total_time = time.time() - start_time
            
            result = OSWorldResult(
                task_id=task.task_id,
                success=evaluation_result["success"],
                accuracy=evaluation_result["accuracy"],
                efficiency=evaluation_result["efficiency"],
                safety=evaluation_result["safety"],
                reasoning_quality=evaluation_result["reasoning_quality"],
                execution_time=total_time,
                actions_taken=execution_result.get("actions", []),
                errors=evaluation_result.get("errors", []),
                metadata={
                    "planning_time": plan_result.get("execution_time", 0),
                    "execution_time": execution_result.get("execution_time", 0),
                    "steps_taken": len(execution_result.get("actions", [])),
                    "module_config": plan_result.get("module_config", {})
                }
            )
            
            # Update statistics
            self._update_evaluation_stats(result)
            
            # Store in memory for learning
            self.memory.learn_from_execution(
                instruction, 
                plan_result, 
                result.success, 
                total_time
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Task execution failed: {e}")
            return OSWorldResult(
                task_id=task.task_id,
                success=False,
                accuracy=0.0,
                efficiency=0.0,
                safety=0.0,
                reasoning_quality=0.0,
                execution_time=time.time() - start_time,
                actions_taken=[],
                errors=[str(e)],
                metadata={"error": "execution_failed"}
            )
    
    def _analyze_screen_state(self) -> Dict:
        """Analyze current screen state using perception module."""
        try:
            # Use coordinate-free perception for better accuracy
            parse_result = self.perception.parse_screen(use_coordinate_free=True)
            
            return {
                "screen_analysis": parse_result,
                "timestamp": time.time(),
                "elements_detected": len(parse_result.get("semantic_regions", {})),
                "interactable_elements": len(parse_result.get("interactable_regions", []))
            }
            
        except Exception as e:
            logger.error(f"Screen analysis failed: {e}")
            return {"error": str(e)}
    
    def _create_planning_context(self, task: OSWorldTask, perception_result: Dict) -> Dict:
        """Create planning context for OSWorld task."""
        return {
            "task_id": task.task_id,
            "category": task.category,
            "difficulty": task.difficulty,
            "expected_actions": task.expected_actions,
            "evaluation_criteria": task.evaluation_criteria,
            "max_steps": self.max_steps,
            "max_time": self.max_time,
            "screen_state": perception_result,
            "osworld_mode": True
        }
    
    def _execute_plan_with_safety(self, plan_result: Dict, task: OSWorldTask, 
                                 start_time: float) -> Dict:
        """Execute plan with safety checks and step limits."""
        try:
            plan = plan_result.get("plan", {})
            actions = plan.get("actions", [])
            
            # Safety checks
            if self.safety_checks:
                actions = self._apply_safety_filters(actions, task)
            
            # Execute with step and time limits
            execution_result = self.execution.execute_plan(
                plan, 
                f"OSWorld Task {task.task_id}"
            )
            
            # Check limits
            current_time = time.time()
            elapsed_time = current_time - start_time
            steps_taken = len(actions)
            
            if elapsed_time > self.max_time:
                logger.warning(f"Task exceeded time limit: {elapsed_time}s > {self.max_time}s")
                execution_result["timeout"] = True
            
            if steps_taken > self.max_steps:
                logger.warning(f"Task exceeded step limit: {steps_taken} > {self.max_steps}")
                execution_result["step_limit_exceeded"] = True
            
            return execution_result
            
        except Exception as e:
            logger.error(f"Safe execution failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "actions": []
            }
    
    def _apply_safety_filters(self, actions: List[Dict], task: OSWorldTask) -> List[Dict]:
        """Apply safety filters to actions."""
        filtered_actions = []
        
        # Dangerous action patterns
        dangerous_patterns = [
            "format", "delete", "remove", "rm", "shutdown", "reboot",
            "sudo", "admin", "root", "system32"
        ]
        
        for action in actions:
            action_str = str(action).lower()
            
            # Check for dangerous actions
            is_dangerous = any(pattern in action_str for pattern in dangerous_patterns)
            
            if not is_dangerous:
                filtered_actions.append(action)
            else:
                logger.warning(f"Filtered dangerous action: {action}")
        
        return filtered_actions
    
    def _evaluate_task_completion(self, task: OSWorldTask, execution_result: Dict, 
                               perception_result: Dict) -> Dict:
        """Evaluate task completion using OSWorld criteria."""
        try:
            # In a full implementation, this would use OSWorld's evaluation framework
            # For now, we'll implement a basic evaluation
            
            success = execution_result.get("success", False)
            actions_taken = execution_result.get("actions", [])
            
            # Accuracy: How well the task was completed
            accuracy = self._calculate_accuracy(task, execution_result, perception_result)
            
            # Efficiency: How efficiently the task was completed
            efficiency = self._calculate_efficiency(task, execution_result)
            
            # Safety: How safely the task was completed
            safety = self._calculate_safety(execution_result)
            
            # Reasoning quality: Quality of planning and decision making
            reasoning_quality = self._calculate_reasoning_quality(
                task, execution_result, perception_result
            )
            
            # Overall success
            overall_success = (
                success and 
                accuracy >= 0.7 and 
                efficiency >= 0.5 and 
                safety >= 0.8
            )
            
            return {
                "success": overall_success,
                "accuracy": accuracy,
                "efficiency": efficiency,
                "safety": safety,
                "reasoning_quality": reasoning_quality,
                "errors": execution_result.get("errors", [])
            }
            
        except Exception as e:
            logger.error(f"Evaluation failed: {e}")
            return {
                "success": False,
                "accuracy": 0.0,
                "efficiency": 0.0,
                "safety": 0.0,
                "reasoning_quality": 0.0,
                "errors": [str(e)]
            }
    
    def _calculate_accuracy(self, task: OSWorldTask, execution_result: Dict, 
                         perception_result: Dict) -> float:
        """Calculate task completion accuracy."""
        # This would use OSWorld's evaluation framework in a full implementation
        # For now, use basic heuristics
        
        success = execution_result.get("success", False)
        if success:
            return 0.9  # High accuracy for successful tasks
        else:
            return 0.3  # Low accuracy for failed tasks
    
    def _calculate_efficiency(self, task: OSWorldTask, execution_result: Dict) -> float:
        """Calculate task execution efficiency."""
        actions_taken = len(execution_result.get("actions", []))
        execution_time = execution_result.get("execution_time", 0)
        
        # Efficiency based on action count and time
        action_efficiency = max(0, 1.0 - (actions_taken / self.max_steps))
        time_efficiency = max(0, 1.0 - (execution_time / self.max_time))
        
        return (action_efficiency + time_efficiency) / 2
    
    def _calculate_safety(self, execution_result: Dict) -> float:
        """Calculate safety score."""
        errors = execution_result.get("errors", [])
        
        # High safety if no errors
        if not errors:
            return 1.0
        
        # Reduce safety based on error severity
        dangerous_errors = ["permission", "crash", "corruption", "delete"]
        has_dangerous = any(error.lower() in dangerous_error 
                          for dangerous_error in dangerous_errors 
                          for error in errors)
        
        if has_dangerous:
            return 0.2  # Very low safety
        else:
            return 0.7  # Moderate safety
    
    def _calculate_reasoning_quality(self, task: OSWorldTask, execution_result: Dict,
                                perception_result: Dict) -> float:
        """Calculate reasoning quality score."""
        # This would analyze the quality of planning and decision making
        # For now, use basic heuristics
        
        success = execution_result.get("success", False)
        steps_taken = len(execution_result.get("actions", []))
        
        if success and steps_taken <= 10:
            return 0.9  # High quality: efficient success
        elif success:
            return 0.7  # Medium quality: success but inefficient
        elif steps_taken <= 5:
            return 0.4  # Low quality: failed but tried efficiently
        else:
            return 0.2  # Very low quality: failed and inefficient
    
    def _update_evaluation_stats(self, result: OSWorldResult):
        """Update evaluation statistics."""
        if result.success:
            self.evaluation_stats["successful_tasks"] += 1
        
        self.evaluation_stats["accuracy_scores"].append(result.accuracy)
        self.evaluation_stats["efficiency_scores"].append(result.efficiency)
        self.evaluation_stats["safety_scores"].append(result.safety)
        self.evaluation_stats["reasoning_scores"].append(result.reasoning_quality)
        
        # Update average execution time
        total_tasks = self.evaluation_stats["total_tasks"]
        current_avg = self.evaluation_stats["avg_execution_time"]
        self.evaluation_stats["avg_execution_time"] = (
            (current_avg * (total_tasks - 1) + result.execution_time) / total_tasks
        )
    
    def get_evaluation_stats(self) -> Dict:
        """Get comprehensive evaluation statistics."""
        total = self.evaluation_stats["total_tasks"]
        if total == 0:
            return self.evaluation_stats
        
        return {
            **self.evaluation_stats,
            "success_rate": self.evaluation_stats["successful_tasks"] / total,
            "avg_accuracy": np.mean(self.evaluation_stats["accuracy_scores"]) if self.evaluation_stats["accuracy_scores"] else 0.0,
            "avg_efficiency": np.mean(self.evaluation_stats["efficiency_scores"]) if self.evaluation_stats["efficiency_scores"] else 0.0,
            "avg_safety": np.mean(self.evaluation_stats["safety_scores"]) if self.evaluation_stats["safety_scores"] else 0.0,
            "avg_reasoning_quality": np.mean(self.evaluation_stats["reasoning_scores"]) if self.evaluation_stats["reasoning_scores"] else 0.0
        }


class OSWorldIntegration:
    """
    Main OSWorld integration module for CecilOs.
    Provides interface for OSWorld benchmark evaluation.
    """
    
    def __init__(self, orchestration_module, perception_module, planning_module, 
                 execution_module, memory_module):
        self.agent = OSWorldAgent(
            orchestration_module, perception_module, planning_module,
            execution_module, memory_module
        )
        
        # OSWorld configuration
        self.benchmark_mode = "evaluation"  # "evaluation" or "training"
        self.task_categories = ["web", "productivity", "system", "file_management"]
        self.difficulty_levels = ["easy", "medium", "hard"]
        
    def run_evaluation(self, task_list: List[OSWorldTask]) -> List[OSWorldResult]:
        """Run OSWorld evaluation on a list of tasks."""
        logger.info(f"Starting OSWorld evaluation with {len(task_list)} tasks")
        
        results = []
        
        for i, task in enumerate(task_list):
            logger.info(f"Executing task {i+1}/{len(task_list)}: {task.task_id}")
            
            try:
                result = self.agent.execute_task(task)
                results.append(result)
                
                # Log intermediate results
                logger.info(
                    f"Task {task.task_id}: "
                    f"{'SUCCESS' if result.success else 'FAILED'} "
                    f"(accuracy: {result.accuracy:.2f}, "
                    f"efficiency: {result.efficiency:.2f})"
                )
                
            except Exception as e:
                logger.error(f"Task {task.task_id} failed with exception: {e}")
                results.append(OSWorldResult(
                    task_id=task.task_id,
                    success=False,
                    accuracy=0.0,
                    efficiency=0.0,
                    safety=0.0,
                    reasoning_quality=0.0,
                    execution_time=0.0,
                    actions_taken=[],
                    errors=[str(e)],
                    metadata={"exception": True}
                ))
        
        return results
    
    def generate_evaluation_report(self, results: List[OSWorldResult]) -> Dict:
        """Generate comprehensive evaluation report."""
        if not results:
            return {"error": "No results to report"}
        
        # Calculate statistics
        total_tasks = len(results)
        successful_tasks = sum(1 for r in results if r.success)
        success_rate = successful_tasks / total_tasks
        
        avg_accuracy = sum(r.accuracy for r in results) / total_tasks
        avg_efficiency = sum(r.efficiency for r in results) / total_tasks
        avg_safety = sum(r.safety for r in results) / total_tasks
        avg_reasoning = sum(r.reasoning_quality for r in results) / total_tasks
        avg_execution_time = sum(r.execution_time for r in results) / total_tasks
        
        # Category-wise performance
        category_performance = {}
        for result in results:
            # Extract category from task_id or metadata
            category = result.metadata.get("category", "unknown")
            if category not in category_performance:
                category_performance[category] = {"success": 0, "total": 0}
            
            category_performance[category]["total"] += 1
            if result.success:
                category_performance[category]["success"] += 1
        
        # Calculate success rates by category
        for category in category_performance:
            cat_stats = category_performance[category]
            category_performance[category]["success_rate"] = (
                cat_stats["success"] / cat_stats["total"]
            )
        
        return {
            "summary": {
                "total_tasks": total_tasks,
                "successful_tasks": successful_tasks,
                "success_rate": success_rate,
                "avg_accuracy": avg_accuracy,
                "avg_efficiency": avg_efficiency,
                "avg_safety": avg_safety,
                "avg_reasoning_quality": avg_reasoning,
                "avg_execution_time": avg_execution_time
            },
            "category_performance": category_performance,
            "detailed_results": [
                {
                    "task_id": r.task_id,
                    "success": r.success,
                    "accuracy": r.accuracy,
                    "efficiency": r.efficiency,
                    "safety": r.safety,
                    "reasoning_quality": r.reasoning_quality,
                    "execution_time": r.execution_time,
                    "steps_taken": len(r.actions_taken),
                    "errors": r.errors
                }
                for r in results
            ],
            "agent_stats": self.agent.get_evaluation_stats()
        }
    
    def prepare_for_benchmark(self) -> bool:
        """Prepare CecilOs for OSWorld benchmark."""
        try:
            logger.info("Preparing CecilOs for OSWorld benchmark")
            
            # Enable all modules
            # This would ensure all modules are properly configured
            
            # Set benchmark-specific configurations
            self.agent.max_steps = 50
            self.agent.max_time = 300
            self.agent.safety_checks = True
            
            logger.info("CecilOs prepared for OSWorld benchmark")
            return True
            
        except Exception as e:
            logger.error(f"Benchmark preparation failed: {e}")
            return False
