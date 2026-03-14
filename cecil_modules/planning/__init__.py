"""
Planning Module - Phase 2.2

Implements modular planning with OpenClaw integration, LLM planning, and skill cache.
Inspired by Simular S2 modular architecture with specialized planning components.
"""

import logging
import time
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum

logger = logging.getLogger("cecil.planning")


class PlanningStrategy(Enum):
    """Planning strategy enumeration."""
    CACHE_FIRST = "cache_first"
    OPENCLAW_ENHANCED = "openclaw_enhanced"
    LLM_PLANNING = "llm_planning"
    HYBRID = "hybrid"


class PlanQuality(Enum):
    """Plan quality assessment."""
    EXCELLENT = "excellent"
    GOOD = "good"
    ACCEPTABLE = "acceptable"
    POOR = "poor"
    FAILED = "failed"


class ModularPlanner:
    """
    Modular planner that can use different planning strategies.
    Orchestrates between cache, OpenClaw, and LLM planning.
    """
    
    def __init__(self, skill_cache, enhanced_openclaw, llm_engine, perception_module):
        self.skill_cache = skill_cache
        self.enhanced_openclaw = enhanced_openclaw
        self.llm_engine = llm_engine
        self.perception_module = perception_module
        
        self.stats = {
            "total_plans": 0,
            "cache_hits": 0,
            "openclaw_plans": 0,
            "llm_plans": 0,
            "hybrid_plans": 0,
            "failed_plans": 0,
            "avg_plan_time": 0.0
        }
        
        self.strategy_weights = {
            PlanningStrategy.CACHE_FIRST: 0.3,
            PlanningStrategy.OPENCLAW_ENHANCED: 0.4,
            PlanningStrategy.LLM_PLANNING: 0.2,
            PlanningStrategy.HYBRID: 0.1
        }
    
    def plan(self, command: str, context: Dict = None, strategy: PlanningStrategy = PlanningStrategy.HYBRID) -> Dict:
        """
        Generate plan using specified strategy.
        """
        start_time = time.time()
        self.stats["total_plans"] += 1
        
        try:
            context = context or {}
            
            if strategy == PlanningStrategy.CACHE_FIRST:
                result = self._plan_cache_first(command, context)
            elif strategy == PlanningStrategy.OPENCLAW_ENHANCED:
                result = self._plan_openclaw_enhanced(command, context)
            elif strategy == PlanningStrategy.LLM_PLANNING:
                result = self._plan_llm(command, context)
            elif strategy == PlanningStrategy.HYBRID:
                result = self._plan_hybrid(command, context)
            else:
                result = {"error": f"Unknown strategy: {strategy}"}
            
            # Add metadata
            result["planning_time"] = time.time() - start_time
            result["strategy"] = strategy.value
            result["quality"] = self._assess_plan_quality(result)
            
            # Update stats
            self._update_stats(strategy, result.get("quality", PlanQuality.FAILED))
            
            return result
            
        except Exception as e:
            logger.error(f"Planning failed: {e}")
            self.stats["failed_plans"] += 1
            return {
                "error": str(e),
                "strategy": strategy.value,
                "quality": PlanQuality.FAILED.value,
                "planning_time": time.time() - start_time
            }
    
    def _plan_cache_first(self, command: str, context: Dict) -> Dict:
        """Plan with cache-first strategy."""
        # Try cache first
        cached_plan = self.skill_cache.query(command, threshold=0.85)
        if cached_plan:
            self.stats["cache_hits"] += 1
            return {
                "source": "cache",
                "actions": self._semantic_to_actions(cached_plan.steps),
                "confidence": cached_plan.success_rate,
                "skill_id": cached_plan.id,
                "reasoning": "Retrieved from skill cache"
            }
        
        # Fallback to OpenClaw
        return self._plan_openclaw_enhanced(command, context)
    
    def _plan_openclaw_enhanced(self, command: str, context: Dict) -> Dict:
        """Plan with enhanced OpenClaw."""
        active_app = context.get("active_app", "")
        keybindings = context.get("keybindings", "")
        screenshot_path = context.get("screenshot_path")
        
        # Use enhanced OpenClaw planner
        plan_result = self.enhanced_openclaw.plan_with_enhancement(
            command, active_app, keybindings, screenshot_path
        )
        
        if plan_result and plan_result.get("source") != "error":
            self.stats["openclaw_plans"] += 1
            return plan_result
        else:
            return {
                "source": "openclaw_failed",
                "actions": [],
                "error": plan_result.get("error", "OpenClaw planning failed"),
                "reasoning": "OpenClaw planning failed"
            }
    
    def _plan_llm(self, command: str, context: Dict) -> Dict:
        """Plan with LLM engine."""
        if not self.llm_engine.available:
            return {
                "source": "llm_unavailable",
                "actions": [],
                "error": "LLM engine not available",
                "reasoning": "LLM engine not available"
            }
        
        try:
            # Generate screen context
            screen_layout = self._generate_screen_layout(context)
            
            # Plan with LLM
            result = self.llm_engine.generate_plan(
                command, screen_layout,
                keybinding_context=context.get("keybindings", ""),
                active_app=context.get("active_app", "")
            )
            
            self.stats["llm_plans"] += 1
            return {
                "source": "llm",
                "actions": result.get("actions", []),
                "reasoning": result.get("reasoning", ""),
                "confidence": 0.7  # LLM confidence estimate
            }
            
        except Exception as e:
            return {
                "source": "llm_failed",
                "actions": [],
                "error": str(e),
                "reasoning": "LLM planning failed"
            }
    
    def _plan_hybrid(self, command: str, context: Dict) -> Dict:
        """Plan with hybrid strategy combining multiple approaches."""
        plans = []
        
        # Try cache first
        cache_plan = self._plan_cache_first(command, context)
        if cache_plan.get("source") == "cache":
            plans.append(("cache", cache_plan, 0.9))  # High confidence for cache hits
        
        # Try OpenClaw
        openclaw_plan = self._plan_openclaw_enhanced(command, context)
        if openclaw_plan.get("source") not in ["openclaw_failed", "error"]:
            confidence = self._calculate_plan_confidence(openclaw_plan)
            plans.append(("openclaw", openclaw_plan, confidence))
        
        # Try LLM
        llm_plan = self._plan_llm(command, context)
        if llm_plan.get("source") not in ["llm_unavailable", "llm_failed", "error"]:
            confidence = self._calculate_plan_confidence(llm_plan)
            plans.append(("llm", llm_plan, confidence))
        
        # Select best plan
        if not plans:
            return {
                "source": "hybrid_failed",
                "actions": [],
                "error": "All planning strategies failed",
                "reasoning": "No successful planning strategy available"
            }
        
        # Sort by confidence and select best
        plans.sort(key=lambda x: x[2], reverse=True)
        best_strategy, best_plan, best_confidence = plans[0]
        
        self.stats["hybrid_plans"] += 1
        
        return {
            "source": f"hybrid_{best_strategy}",
            "actions": best_plan.get("actions", []),
            "reasoning": f"Selected {best_strategy} plan (confidence: {best_confidence:.2f})",
            "confidence": best_confidence,
            "alternative_plans": [plan for _, plan, _ in plans[1:3]]  # Top 3 alternatives
        }
    
    def _generate_screen_layout(self, context: Dict) -> str:
        """Generate screen layout for LLM planning."""
        screenshot_path = context.get("screenshot_path")
        
        if screenshot_path:
            # Use coordinate-free parsing
            parse_data = self.perception_module.parse_screen(
                use_coordinate_free=True, 
                screenshot_path=screenshot_path
            )
            
            if "error" not in parse_data:
                return self.perception_module.generate_planning_context(
                    use_coordinate_free=True,
                    screenshot_path=screenshot_path
                )
        
        return "[]"
    
    def _semantic_to_actions(self, semantic_steps: List) -> List[Dict]:
        """Convert semantic steps to executable actions."""
        actions = []
        
        for step in semantic_steps:
            action = {
                "type": step.intent,
                "target": step.target,
                "text": step.text,
                "key": step.key,
                "app": step.app
            }
            
            # Remove None values
            action = {k: v for k, v in action.items() if v is not None}
            actions.append(action)
        
        return actions
    
    def _calculate_plan_confidence(self, plan: Dict) -> float:
        """Calculate confidence score for a plan."""
        base_confidence = plan.get("confidence", 0.5)
        
        # Adjust based on source
        source = plan.get("source", "")
        if source == "cache":
            return min(base_confidence + 0.2, 1.0)
        elif source == "openclaw_enhanced":
            return min(base_confidence + 0.1, 1.0)
        elif source == "llm":
            return base_confidence
        else:
            return max(base_confidence - 0.2, 0.0)
    
    def _assess_plan_quality(self, plan: Dict) -> PlanQuality:
        """Assess the quality of a generated plan."""
        if "error" in plan:
            return PlanQuality.FAILED
        
        actions = plan.get("actions", [])
        confidence = plan.get("confidence", 0.0)
        source = plan.get("source", "")
        
        # Quality assessment based on multiple factors
        if not actions:
            return PlanQuality.POOR
        
        if confidence >= 0.9 and len(actions) <= 5:
            return PlanQuality.EXCELLENT
        elif confidence >= 0.7 and len(actions) <= 10:
            return PlanQuality.GOOD
        elif confidence >= 0.5 and len(actions) <= 15:
            return PlanQuality.ACCEPTABLE
        else:
            return PlanQuality.POOR
    
    def _update_stats(self, strategy: PlanningStrategy, quality: PlanQuality):
        """Update planning statistics."""
        # Update strategy-specific stats
        if strategy == PlanningStrategy.CACHE_FIRST:
            # Already updated in _plan_cache_first
            pass
        elif strategy == PlanningStrategy.OPENCLAW_ENHANCED:
            # Already updated in _plan_openclaw_enhanced
            pass
        elif strategy == PlanningStrategy.LLM_PLANNING:
            # Already updated in _plan_llm
            pass
        elif strategy == PlanningStrategy.HYBRID:
            # Already updated in _plan_hybrid
            pass
    
    def get_stats(self) -> Dict:
        """Get planning statistics."""
        total = self.stats["total_plans"]
        if total == 0:
            return self.stats
        
        return {
            **self.stats,
            "cache_hit_rate": self.stats["cache_hits"] / total,
            "openclaw_success_rate": self.stats["openclaw_plans"] / total,
            "llm_success_rate": self.stats["llm_plans"] / total,
            "hybrid_success_rate": self.stats["hybrid_plans"] / total,
            "failure_rate": self.stats["failed_plans"] / total
        }
    
    def update_strategy_weights(self, weights: Dict[PlanningStrategy, float]):
        """Update strategy weights for hybrid planning."""
        total_weight = sum(weights.values())
        if total_weight > 0:
            self.strategy_weights = {
                strategy: weight / total_weight 
                for strategy, weight in weights.items()
            }


class PlanValidator:
    """
    Validates generated plans before execution.
    Checks for safety, feasibility, and correctness.
    """
    
    def __init__(self):
        self.validation_rules = {
            "max_actions": 20,
            "max_wait_time": 30,
            "dangerous_actions": ["format", "delete", "remove", "rm"],
            "required_confirmations": ["format", "delete", "remove", "rm"]
        }
    
    def validate_plan(self, plan: Dict, context: Dict = None) -> Dict:
        """
        Validate a generated plan.
        Returns validation result with recommendations.
        """
        try:
            actions = plan.get("actions", [])
            source = plan.get("source", "")
            
            validation_result = {
                "valid": True,
                "warnings": [],
                "errors": [],
                "recommendations": [],
                "requires_confirmation": False
            }
            
            # Check action count
            if len(actions) > self.validation_rules["max_actions"]:
                validation_result["warnings"].append(
                    f"Plan has {len(actions)} actions (max: {self.validation_rules['max_actions']})"
                )
            
            # Check for dangerous actions
            dangerous_found = []
            for i, action in enumerate(actions):
                action_text = str(action).lower()
                for dangerous in self.validation_rules["dangerous_actions"]:
                    if dangerous in action_text:
                        dangerous_found.append((i, dangerous))
            
            if dangerous_found:
                validation_result["warnings"].extend([
                    f"Dangerous action found at step {idx}: {action}"
                    for idx, action in dangerous_found
                ])
                validation_result["requires_confirmation"] = True
            
            # Check action sequence
            if self._has_logical_errors(actions):
                validation_result["errors"].append("Plan contains logical errors")
                validation_result["valid"] = False
            
            # Add recommendations
            if source == "llm" and len(actions) > 10:
                validation_result["recommendations"].append(
                    "Consider breaking down complex LLM plans into smaller steps"
                )
            
            return validation_result
            
        except Exception as e:
            return {
                "valid": False,
                "errors": [f"Validation failed: {e}"],
                "warnings": [],
                "recommendations": [],
                "requires_confirmation": False
            }
    
    def _has_logical_errors(self, actions: List[Dict]) -> bool:
        """Check for logical errors in action sequence."""
        # Simple checks for now
        for i, action in enumerate(actions):
            action_type = action.get("type", "")
            
            # Check for invalid action types
            valid_types = ["tap", "double_click", "right_click", "type", "key", 
                          "scroll", "wait", "launch_app", "close_window", "hover"]
            if action_type not in valid_types:
                return True
        
        return False


class PlanningModule:
    """
    Main planning module orchestrating all planning capabilities.
    Integrates modular planner with validation and learning.
    """
    
    def __init__(self, skill_cache, enhanced_openclaw, llm_engine, perception_module):
        self.modular_planner = ModularPlanner(
            skill_cache, enhanced_openclaw, llm_engine, perception_module
        )
        self.validator = PlanValidator()
        self.learning_enabled = True
        
    def plan_and_validate(self, command: str, context: Dict = None, 
                         strategy: PlanningStrategy = PlanningStrategy.HYBRID) -> Dict:
        """
        Generate and validate a plan.
        """
        # Generate plan
        plan = self.modular_planner.plan(command, context, strategy)
        
        # Validate plan
        validation = self.validator.validate_plan(plan, context)
        
        # Combine results
        result = {
            "plan": plan,
            "validation": validation,
            "ready_for_execution": validation["valid"] and not validation["errors"],
            "requires_user_confirmation": validation["requires_confirmation"]
        }
        
        return result
    
    def learn_from_execution(self, command: str, plan: Dict, success: bool, 
                             execution_time: float):
        """Learn from execution results."""
        if not self.learning_enabled:
            return
        
        # Store successful plans in cache
        if success and plan.get("source") in ["openclaw_enhanced", "llm", "hybrid_openclaw"]:
            self.modular_planner.enhanced_openclaw.store_execution_result(
                plan.get("source"), command, plan.get("actions", []), success
            )
        
        # Update strategy weights based on performance
        self._update_strategy_weights(plan.get("strategy"), success, execution_time)
    
    def _update_strategy_weights(self, strategy: str, success: bool, execution_time: float):
        """Update strategy weights based on performance."""
        # Simple weight adjustment based on success
        current_weights = self.modular_planner.strategy_weights
        
        try:
            strategy_enum = PlanningStrategy(strategy)
            if success:
                # Increase weight for successful strategies
                current_weights[strategy_enum] = min(current_weights[strategy_enum] * 1.1, 0.6)
            else:
                # Decrease weight for failed strategies
                current_weights[strategy_enum] = max(current_weights[strategy_enum] * 0.9, 0.1)
            
            self.modular_planner.update_strategy_weights(current_weights)
            
        except ValueError:
            logger.warning(f"Unknown strategy for weight update: {strategy}")
    
    def get_stats(self) -> Dict:
        """Get comprehensive planning statistics."""
        return {
            "planner_stats": self.modular_planner.get_stats(),
            "strategy_weights": {
                strategy.value: weight 
                for strategy, weight in self.modular_planner.strategy_weights.items()
            }
        }
