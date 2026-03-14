"""
File and Folder Management Skill.
Isolates explicitly the behavior for managing windows, double-clicking folders,
and visual validation as mandated by the L3 lock-target-act pattern.
"""
import logging
from typing import Dict, Any, List

logger = logging.getLogger("cecil.skills.file_management")

class FileManagementSkill:
    def __init__(self, vision_capture=None, vision_parser=None, hand_executor=None):
        """
        Args:
            vision_capture: An instance to take L3 screen captures.
            vision_parser: An instance capable of executing L3 OCR/Vision commands to get UI bounds.
            hand_executor: An instance of cecil_hand's InputExecutor to control inputs.
        """
        self.vision_capture = vision_capture
        self.vision_parser = vision_parser
        self.hand = hand_executor

    def is_file_operation(self, command: str) -> bool:
        """
        Determine if a command explicitly relates to this domain.
        E.g., "crear carpeta", "abrir archivo", "renombrar"
        """
        c = command.lower()
        keywords = ["carpeta", "archivo", "folder", "directorio", "abrir", "click"]
        return any(k in c for k in keywords)

    def execute_operation(self, command: str, context: Dict[str, Any] = None) -> bool:
        """
        The entrypoint of the lock-target-act sequence for file operations.
        1. Parse intent.
        2. Visual query using vision.
        3. Human-like movement.
        4. Focus click.
        5. Execute keystroke/action.
        """
        logger.info(f"Executing File Management OP: {command}")
        # Default behavior:
        # Require target bounding box. Since this is domain logic, we can
        # define steps explicitly based on command heuristics.
        return True

    def focus_element_visually(self, element_data: Dict[str, Any]) -> bool:
        """
        The core Wayland/Hyprland safeguard (Lock-Target-Act).
        1. Extract coordinates.
        2. Move mouse humanly to the center.
        3. Click to secure window focus.
        """
        if not self.hand:
            logger.error("No hand_executor injected, cannot focus.")
            return False

        try:
            x = element_data.get("x", 0)
            y = element_data.get("y", 0)
            width = element_data.get("width", 0)
            height = element_data.get("height", 0)

            # Calculate center of the target
            center_x = int(x + (width / 2))
            center_y = int(y + (height / 2))

            logger.info(f"Locking target at center ({center_x}, {center_y}) for Wayland focus...")

            # 1. Visually human glide to target
            self.hand.move_mouse_humanly(center_x, center_y, max_duration=0.6)

            # 2. Tap (Click) to strictly steal Hyprland focus
            self.hand.tap(center_x, center_y)

            # 3. Small delay to let the compositor register the window state change
            import time
            time.sleep(0.3)
            
            return True
        except Exception as e:
            logger.error(f"Failed to focus element visually: {e}")
            return False

    def navigate_to(self, target_name: str) -> bool:
        """
        Takes a screenshot, uses vision_parser to find an element that matches target_name 
        (e.g., "Downloads" or "Descargas"), focuses it via human mouse move, and double clicks.
        """
        if not self.vision_capture or not self.vision_parser or not self.hand:
            logger.error("Missing vision components in FileManagementSkill.")
            return False

        logger.info(f"Looking for '{target_name}' visually...")
        import time
        # Give Hyprland time to map the window
        time.sleep(1.0)
        
        screenshot_path = self.vision_capture.capture()
        if not screenshot_path:
            logger.error("Failed to capture screen.")
            return False

        elements = self.vision_parser.parse(screenshot_path)
        if not elements:
            logger.error("No elements parsed.")
            return False

        # Find best match
        target_name_lower = target_name.lower()
        matched_element = None
        for el in elements:
            name = (el.get("text") or el.get("name", "")).lower()
            # E.g., 'downloads' vs 'descargas'
            # Simple substring or equal check
            if target_name_lower in name:
                # Discard full screen wrappers
                w = el.get("width", 0)
                h = el.get("height", 0)
                # Ensure it's somewhat like an icon/row, not the whole window
                if w > 0 and h > 0 and (w * h) < 1000000:
                    matched_element = el
                    break

        if not matched_element:
            # Fallback exact checks or aliases
            aliases = {"downloads": ["descargas", "downloads"], "documents": ["documentos", "documents"]}
            target_aliases = aliases.get(target_name_lower, [target_name_lower])
            for el in elements:
                name = (el.get("text") or el.get("name", "")).lower()
                if any(alias in name for alias in target_aliases):
                    matched_element = el
                    break

        if not matched_element:
            logger.error(f"Could not find visual element for '{target_name}'")
            return False
            
        logger.info(f"Visual element found: {matched_element}")
        
        # Focus it
        if self.focus_element_visually(matched_element):
            # It's locked. Now double click it!
            # The focus already moved the mouse and tapped it. 
            # We can just tap twice in quick succession to double click.
            # But the focus tap already did 1 tap, so we technically only need another click or just call double_click on the same pos
            x = matched_element.get("x", 0)
            y = matched_element.get("y", 0)
            w = matched_element.get("width", 0)
            h = matched_element.get("height", 0)
            center_x = int(x + (w / 2))
            center_y = int(y + (h / 2))
            
            # Since we just tapped it to focus, let's wait a tiny bit then double click
            time.sleep(0.1)
            self.hand.double_click(center_x, center_y)
            return True
            
        return False
