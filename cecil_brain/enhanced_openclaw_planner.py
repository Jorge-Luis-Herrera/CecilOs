"""
Enhanced OpenClaw Planner - Phase 1.1

Deep integration with OpenClaw CLI, vision enhancement, and skill cache bridge.
Transforms OpenClaw from fallback to primary planner with GUI-Actor coordinate-free grounding.
"""

import json
import logging
import os
import subprocess
import time
from typing import Dict, List, Optional, Tuple, Any

logger = logging.getLogger("cecil.enhanced_openclaw")


class VisionEnhancementBridge:
    """
    Bridge between CecilOs vision system and OpenClaw planner.
    Implements GUI-Actor coordinate-free grounding methodology.
    """
    
    def __init__(self, vision_parser, screen_capture):
        self.vision_parser = vision_parser
        self.screen_capture = screen_capture
        
    def parse_screen_for_openclaw(self, screenshot_path: str = None) -> str:
        """
        Parse screen and convert to OpenClaw-compatible format.
        Implements coordinate-free semantic grounding.
        """
        try:
            # Capture screenshot if not provided
            if not screenshot_path:
                screenshot_path = self.screen_capture.capture()
            
            # Parse with existing vision system
            elements = self.vision_parser.parse(screenshot_path)
            
            # Convert to coordinate-free semantic format
            semantic_elements = []
            for element in elements:
                semantic_elem = {
                    "type": element.get("role", "unknown"),
                    "label": element.get("name", ""),
                    "description": element.get("description", ""),
                    "semantic_region": self._generate_semantic_region(element),
                    "interactable": self._is_interactable(element),
                    "fallback_key": self._get_fallback_keybinding(element)
                }
                semantic_elements.append(semantic_elem)
            
            # Generate OpenClaw context
            context = self._generate_openclaw_context(semantic_elements)
            return context
            
        except Exception as e:
            logger.error(f"Vision enhancement error: {e}")
            return "Screen parsing unavailable"
    
    def _generate_semantic_region(self, element: Dict) -> str:
        """Generate semantic region identifier (coordinate-free)."""
        elem_type = element.get("role", "unknown")
        elem_name = element.get("name", "")
        
        # Semantic region based on type and position
        if elem_type == "button":
            return f"button_{elem_name.lower().replace(' ', '_')}"
        elif elem_type == "text":
            return f"text_field_{elem_name.lower().replace(' ', '_')}"
        elif elem_type == "menu":
            return f"menu_{elem_name.lower().replace(' ', '_')}"
        else:
            return f"element_{elem_type}_{hash(elem_name) % 1000}"
    
    def _is_interactable(self, element: Dict) -> bool:
        """Determine if element is interactable."""
        interactable_roles = {"button", "text", "menu", "link", "checkbox", "radio"}
        return element.get("role", "").lower() in interactable_roles
    
    def _get_fallback_keybinding(self, element: Dict) -> Optional[str]:
        """Get fallback keybinding for element."""
        # Common fallbacks based on element type
        role = element.get("role", "").lower()
        name = element.get("name", "").lower()
        
        fallbacks = {
            "button": ["Enter", "Space"],
            "menu": ["Alt", "F10"],
            "text": ["Tab", "Enter"]
        }
        
        if role in fallbacks:
            return fallbacks[role][0]
        return None
    
    def _generate_openclaw_context(self, elements: List[Dict]) -> str:
        """Generate OpenClaw-compatible context from semantic elements."""
        context_lines = ["Screen Analysis (Coordinate-Free Grounding):"]
        
        for elem in elements:
            if elem["interactable"]:
                line = f"- {elem['type']}: '{elem['label']}' (region: {elem['semantic_region']})"
                if elem["fallback_key"]:
                    line += f" [fallback: {elem['fallback_key']}]"
                context_lines.append(line)
        
        return "\n".join(context_lines)


class SkillCacheBridge:
    """
    Bridge between skill cache and OpenClaw planner.
    Enables cache lookup before OpenClaw planning and storage after.
    """
    
    def __init__(self, skill_cache):
        self.skill_cache = skill_cache
        
    def query_cache_for_openclaw(self, command: str, visual_context: str = "") -> Optional[Dict]:
        """
        Query skill cache before calling OpenClaw.
        Returns cached plan if available with high confidence.
        """
        try:
            # Query cache with semantic similarity
            cached_skill = self.skill_cache.query(command, threshold=0.85)
            
            if cached_skill is not None:
                logger.info(f"Cache hit for OpenClaw: {cached_skill.command}")
                
                # Convert semantic steps to OpenClaw actions
                openclaw_actions = self._semantic_to_openclaw_actions(cached_skill.steps)
                
                return {
                    "source": "cache",
                    "actions": openclaw_actions,
                    "confidence": cached_skill.success_rate,
                    "skill_id": cached_skill.id
                }
        
        except Exception as e:
            logger.warning(f"Cache query error: {e}")
            
        return None
    
    def store_openclaw_plan(self, command: str, openclaw_actions: List[Dict], 
                           success: bool, visual_context: str = "") -> str:
        """
        Store successful OpenClaw plan in skill cache.
        Converts OpenClaw actions to semantic steps.
        """
        try:
            # Convert OpenClaw actions to semantic steps
            semantic_steps = self._openclaw_to_semantic_steps(openclaw_actions)
            
            # Create cached skill
            from cecil_brain.skill_cache import CachedSkill, SemanticStep
            
            skill = CachedSkill(
                id=self._generate_skill_id(command),
                command=command,
                command_embedding=[],  # Will be populated by cache
                steps=semantic_steps,
                app_context="",  # Extract from visual context if needed
                success_count=1 if success else 0,
                failure_count=0 if success else 1,
                last_executed=time.time(),
                created_at=time.time()
            )
            
            # Store in cache
            self.skill_cache.store(skill)
            
            logger.info(f"Stored OpenClaw plan: {len(semantic_steps)} steps")
            return skill.id
            
        except Exception as e:
            logger.error(f"Failed to store OpenClaw plan: {e}")
            return ""
    
    def _semantic_to_openclaw_actions(self, semantic_steps: List) -> List[Dict]:
        """Convert semantic steps to OpenClaw action format."""
        actions = []
        
        for step in semantic_steps:
            action = {
                "action": step.intent,
                "target": step.target,
                "text": step.text,
                "key": step.key,
                "app": step.app
            }
            
            # Add coordinate information if available (fallback)
            if hasattr(step, 'metadata') and 'coordinates' in step.metadata:
                action.update(step.metadata['coordinates'])
            
            # Remove None values
            action = {k: v for k, v in action.items() if v is not None}
            actions.append(action)
        
        return actions
    
    def _openclaw_to_semantic_steps(self, openclaw_actions: List[Dict]) -> List:
        """Convert OpenClaw actions to semantic steps."""
        from cecil_brain.skill_cache import SemanticStep
        
        semantic_steps = []
        
        for action in openclaw_actions:
            # Map OpenClaw action types to semantic intents
            intent_map = {
                "tap": "click_button",
                "double_click": "double_click",
                "right_click": "right_click",
                "type": "type_text",
                "key": "key_press",
                "launch_app": "launch_app",
                "close_window": "close_window"
            }
            
            intent = intent_map.get(action.get("action", ""), "unknown")
            
            step = SemanticStep(
                intent=intent,
                target=action.get("target", ""),
                text=action.get("text", ""),
                key=action.get("key", ""),
                app=action.get("app", ""),
                fallback=action.get("fallback_key", ""),
                metadata={
                    "coordinates": {
                        "x": action.get("x"),
                        "y": action.get("y")
                    }
                }
            )
            
            semantic_steps.append(step)
        
        return semantic_steps
    
    def _generate_skill_id(self, command: str) -> str:
        """Generate unique skill ID."""
        import hashlib
        return hashlib.md5(f"{command}_{time.time()}".encode()).hexdigest()


class EnhancedOpenClawPlanner:
    """
    Enhanced OpenClaw Planner with vision enhancement and skill cache integration.
    Transforms OpenClaw from fallback to primary planner.
    """
    
    def __init__(self, skill_cache, vision_parser, screen_capture):
        self.base_planner = self._create_base_planner()
        self.skill_cache_bridge = SkillCacheBridge(skill_cache)
        self.vision_bridge = VisionEnhancementBridge(vision_parser, screen_capture)
        self.last_error = ""
        self.stats = {
            "cache_hits": 0,
            "openclaw_calls": 0,
            "vision_enhancements": 0,
            "total_plans": 0
        }
    
    def _create_base_planner(self):
        """Create base OpenClaw planner (reuse existing implementation)."""
        # Import existing OpenClawPlanner
        import sys
        import os
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        
        from cecil_simple import OpenClawPlanner
        return OpenClawPlanner()
    
    def plan_with_enhancement(self, command: str, active_app: str = "", 
                              keybindings: str = "", screenshot_path: str = None) -> Dict:
        """
        Enhanced planning with vision enhancement and skill cache integration.
        Returns comprehensive plan with source tracking.
        """
        self.stats["total_plans"] += 1
        
        try:
            # Step 1: Check skill cache first
            visual_context = self.vision_bridge.parse_screen_for_openclaw(screenshot_path)
            cached_plan = self.skill_cache_bridge.query_cache_for_openclaw(command, visual_context)
            
            if cached_plan:
                self.stats["cache_hits"] += 1
                logger.info(f"Using cached plan: {cached_plan['skill_id']}")
                return cached_plan
            
            # Step 2: Generate enhanced context for OpenClaw
            enhanced_context = self._build_enhanced_context(
                command, active_app, keybindings, visual_context
            )
            
            # Step 3: Call OpenClaw with enhanced context
            self.stats["openclaw_calls"] += 1
            openclaw_actions = self.base_planner.plan(command, active_app, enhanced_context)
            
            if openclaw_actions:
                self.stats["vision_enhancements"] += 1
                
                return {
                    "source": "openclaw_enhanced",
                    "actions": openclaw_actions,
                    "context": enhanced_context,
                    "visual_context": visual_context,
                    "confidence": 0.8  # OpenClaw confidence estimate
                }
            else:
                self.last_error = self.base_planner.last_error or "OpenClaw failed to generate plan"
                return {"source": "error", "error": self.last_error}
        
        except Exception as e:
            self.last_error = f"Enhanced planning error: {e}"
            logger.error(self.last_error)
            return {"source": "error", "error": self.last_error}
    
    def _build_enhanced_context(self, command: str, active_app: str, 
                               keybindings: str, visual_context: str) -> str:
        """Build enhanced context for OpenClaw with vision enhancement."""
        context_parts = [
            f"Command: {command}",
            f"Active App: {active_app}",
            "",
            "Keybindings:",
            keybindings,
            "",
            "Visual Analysis (Coordinate-Free Grounding):",
            visual_context,
            "",
            "Planning Instructions:",
            "- Use coordinate-free semantic regions when possible",
            "- Prefer semantic targets over raw coordinates",
            "- Include fallback keybindings for robustness",
            "- Consider visual context for optimal action selection"
        ]
        
        return "\n".join(context_parts)
    
    def store_execution_result(self, plan_source: str, command: str, actions: List[Dict], 
                              success: bool, plan_id: str = None):
        """Store execution result in skill cache for learning."""
        if plan_source == "openclaw_enhanced" and success:
            self.skill_cache_bridge.store_openclaw_plan(command, actions, success)
            logger.info(f"Stored successful OpenClaw plan for: {command}")
    
    def get_stats(self) -> Dict:
        """Get planning statistics."""
        total = self.stats["total_plans"]
        if total == 0:
            return self.stats
        
        return {
            **self.stats,
            "cache_hit_rate": self.stats["cache_hits"] / total,
            "openclaw_call_rate": self.stats["openclaw_calls"] / total,
            "vision_enhancement_rate": self.stats["vision_enhancements"] / total
        }
    
    def connect(self) -> bool:
        """Check if OpenClaw is available."""
        return self.base_planner.connect()
    
    @property
    def available(self) -> bool:
        """Check if planner is available."""
        return self.base_planner.available
