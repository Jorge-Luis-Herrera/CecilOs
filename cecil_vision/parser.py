"""
Cecil-Vision Screen Parser.

Parses screen content using the AT-SPI2 accessibility tree (for GTK/Qt apps)
and optionally Tesseract OCR as a fallback for apps that don't expose
accessibility information (e.g., Electron, games).

This approach uses 0 VRAM, preserving GPU memory for the LLM and STT models.
"""

import logging
import subprocess
import json
import os
import shutil
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("cecil.vision")


class ScreenParser:
    """
    Parses screen elements using accessibility APIs and OCR.

    Strategy:
    1. AT-SPI2 (primary): Fast, zero-cost, works with GTK/Qt apps.
    2. Tesseract OCR (fallback): For apps without accessibility support.
    """

    def __init__(self):
        self._has_atspi = self._check_atspi()
        self._has_tesseract = shutil.which("tesseract") is not None
        logger.info(
            f"ScreenParser initialized — "
            f"AT-SPI2: {'available' if self._has_atspi else 'unavailable'}, "
            f"Tesseract: {'available' if self._has_tesseract else 'unavailable'}"
        )

    def _check_atspi(self) -> bool:
        """Check if AT-SPI2 Python bindings are available."""
        try:
            import gi
            gi.require_version("Atspi", "2.0")
            from gi.repository import Atspi
            return True
        except (ImportError, ValueError):
            return False

    def parse_with_atspi(self) -> List[Dict]:
        """
        Parse the currently focused window using AT-SPI2 accessibility tree.

        Returns:
            List of element dictionaries with name, role, position, size, text.
        """
        if not self._has_atspi:
            logger.warning("AT-SPI2 not available")
            return []

        try:
            import gi
            gi.require_version("Atspi", "2.0")
            from gi.repository import Atspi

            desktop = Atspi.get_desktop(0)
            elements = []

            # Iterate over applications
            for i in range(desktop.get_child_count()):
                app = desktop.get_child_at_index(i)
                if app is None:
                    continue

                app_name = app.get_name() or "Unknown"

                # Iterate over windows
                for j in range(app.get_child_count()):
                    window = app.get_child_at_index(j)
                    if window is None:
                        continue

                    # Check if this window is active/focused
                    try:
                        state_set = window.get_state_set()
                        if not state_set.contains(Atspi.StateType.ACTIVE):
                            continue
                    except Exception:
                        continue

                    # Recursively collect elements
                    self._collect_elements(window, elements, app_name, depth=0)

            logger.info(f"AT-SPI2 found {len(elements)} elements")
            return elements

        except Exception as e:
            logger.error(f"AT-SPI2 parsing error: {e}")
            return []

    def _collect_elements(
        self,
        node,
        elements: List[Dict],
        app_name: str,
        depth: int,
        max_depth: int = 15,
    ) -> None:
        """Recursively collect UI elements from the accessibility tree."""
        if depth > max_depth or node is None:
            return

        try:
            import gi
            gi.require_version("Atspi", "2.0")
            from gi.repository import Atspi

            role = node.get_role_name() or ""
            name = node.get_name() or ""

            # Get text content if available
            text = ""
            try:
                text_iface = node.get_text_iface()
                if text_iface:
                    char_count = text_iface.get_character_count()
                    if 0 < char_count < 1000:
                        text = text_iface.get_text(0, char_count) or ""
            except Exception:
                pass

            # Get position and size
            x, y, width, height = 0, 0, 0, 0
            try:
                component = node.get_component_iface()
                if component:
                    rect = component.get_extents(Atspi.CoordType.SCREEN)
                    x, y, width, height = rect.x, rect.y, rect.width, rect.height
            except Exception:
                pass

            # Get state
            state = ""
            try:
                state_set = node.get_state_set()
                states = []
                if state_set.contains(Atspi.StateType.ENABLED):
                    states.append("enabled")
                if state_set.contains(Atspi.StateType.FOCUSED):
                    states.append("focused")
                if state_set.contains(Atspi.StateType.CHECKED):
                    states.append("checked")
                if state_set.contains(Atspi.StateType.EDITABLE):
                    states.append("editable")
                state = ",".join(states)
            except Exception:
                pass

            # Only add elements that are visible and have content
            interactable_roles = {
                "push button", "toggle button", "check box", "radio button",
                "menu item", "text", "entry", "combo box", "slider",
                "tab", "link", "tool bar item", "icon", "list item",
                "tree item", "spin button", "page tab",
            }

            if (
                (name or text)
                and width > 0
                and height > 0
                and (role.lower() in interactable_roles or depth <= 2)
            ):
                elements.append({
                    "name": name,
                    "role": role,
                    "x": x,
                    "y": y,
                    "width": width,
                    "height": height,
                    "text": text or name,
                    "state": state,
                    "app": app_name,
                })

            # Recurse into children
            for k in range(node.get_child_count()):
                child = node.get_child_at_index(k)
                self._collect_elements(child, elements, app_name, depth + 1, max_depth)

        except Exception as e:
            logger.debug(f"Error collecting element at depth {depth}: {e}")

    def parse_with_ocr(self, screenshot_path: str) -> List[Dict]:
        """
        Parse screen content using Tesseract OCR on a screenshot.

        Args:
            screenshot_path: Path to the screenshot PNG.

        Returns:
            List of element dictionaries with text and bounding boxes.
        """
        if not self._has_tesseract:
            logger.warning("Tesseract not available")
            return []

        if not os.path.isfile(screenshot_path):
            logger.error(f"Screenshot not found: {screenshot_path}")
            return []

        try:
            # Run Tesseract with TSV output for bounding boxes
            result = subprocess.run(
                [
                    "tesseract",
                    screenshot_path,
                    "stdout",
                    "--oem", "3",
                    "--psm", "11",  # Sparse text
                    "-l", "spa+eng",  # Spanish + English
                    "tsv",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                logger.error(f"Tesseract failed: {result.stderr}")
                return []

            # Parse TSV output
            elements = []
            lines = result.stdout.strip().split("\n")
            if len(lines) <= 1:
                return elements

            headers = lines[0].split("\t")
            for line in lines[1:]:
                fields = line.split("\t")
                if len(fields) != len(headers):
                    continue

                row = dict(zip(headers, fields))
                text = row.get("text", "").strip()
                
                # Safely parse confidence as float first, then int
                try:
                    conf = int(float(row.get("conf", "0")))
                except ValueError:
                    conf = 0

                if text and conf > 30:  # Filter low-confidence detections
                    elements.append({
                        "name": text,
                        "role": "ocr_text",
                        "x": int(row.get("left", 0)),
                        "y": int(row.get("top", 0)),
                        "width": int(row.get("width", 0)),
                        "height": int(row.get("height", 0)),
                        "text": text,
                        "state": f"conf={conf}",
                        "app": "ocr",
                    })

            logger.info(f"Tesseract OCR found {len(elements)} text elements")
            return elements

        except subprocess.TimeoutExpired:
            logger.error("Tesseract timed out")
            return []
        except Exception as e:
            logger.error(f"Tesseract error: {e}")
            return []

    def parse(self, screenshot_path: Optional[str] = None) -> List[Dict]:
        """
        Parse the screen using the best available method.

        First tries AT-SPI2 (accessibility tree), then falls back to OCR
        if no elements are found.

        Args:
            screenshot_path: Path to screenshot (needed for OCR fallback).

        Returns:
            List of element dictionaries.
        """
        # Try AT-SPI2 first
        elements = []
        if self._has_atspi:
            elements = self.parse_with_atspi()

        # Fallback to OCR if no elements found
        if not elements and screenshot_path and self._has_tesseract:
            logger.info("AT-SPI2 returned no elements, falling back to OCR")
            elements = self.parse_with_ocr(screenshot_path)

        return elements

    def elements_to_json(self, elements: List[Dict]) -> str:
        """Convert element list to a compact JSON string for the LLM."""
        # Simplify for LLM consumption
        simplified = []
        for el in elements:
            simplified.append({
                "name": el.get("text") or el.get("name", ""),
                "role": el.get("role", ""),
                "x": el.get("x", 0) + el.get("width", 0) // 2,  # Center X
                "y": el.get("y", 0) + el.get("height", 0) // 2,  # Center Y
                "state": el.get("state", ""),
            })
        return json.dumps(simplified, ensure_ascii=False, separators=(",", ":"))
