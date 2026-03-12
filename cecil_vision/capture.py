"""
Cecil-Vision Screen Capture.

Captures screenshots on Linux using grim (Wayland) or scrot (X11).
Returns the path to the saved screenshot.
"""

import logging
import os
import shutil
import subprocess
import tempfile
import time
from typing import Optional

logger = logging.getLogger("cecil.vision")


class ScreenCapture:
    """
    Captures screenshots on Linux.

    Supports:
    - grim (Wayland / Hyprland / Sway)
    - scrot (X11)
    - gnome-screenshot (GNOME/X11)
    """

    def __init__(self, output_dir: Optional[str] = None):
        """
        Initialize the screen capture module.

        Args:
            output_dir: Directory to save screenshots. Defaults to /tmp/cecil.
        """
        self._output_dir = output_dir or os.path.join(tempfile.gettempdir(), "cecil")
        os.makedirs(self._output_dir, exist_ok=True)
        self._backend = self._detect_backend()
        logger.info(f"Screen capture using backend: {self._backend}")

    def _detect_backend(self) -> str:
        """Detect available screenshot backend."""
        # Check Wayland session
        wayland = os.environ.get("WAYLAND_DISPLAY") or os.environ.get(
            "XDG_SESSION_TYPE"
        ) == "wayland"

        if wayland and shutil.which("grim"):
            return "grim"

        if shutil.which("scrot"):
            return "scrot"

        if shutil.which("gnome-screenshot"):
            return "gnome-screenshot"

        # Fallback: import if available
        if shutil.which("import"):  # ImageMagick
            return "import"

        logger.error("No screenshot tool found. Install grim (Wayland) or scrot (X11).")
        return "none"

    def capture(self, output_name: Optional[str] = None) -> Optional[str]:
        """
        Capture a screenshot of the entire screen.

        Args:
            output_name: Optional filename (without extension).
                         Defaults to timestamped filename.

        Returns:
            Path to the saved screenshot, or None if capture failed.
        """
        if self._backend == "none":
            logger.error("No screenshot backend available")
            return None

        if output_name is None:
            output_name = f"cecil_screen_{int(time.time() * 1000)}"

        output_path = os.path.join(self._output_dir, f"{output_name}.png")

        try:
            if self._backend == "grim":
                result = subprocess.run(
                    ["grim", output_path],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
            elif self._backend == "scrot":
                result = subprocess.run(
                    ["scrot", output_path],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
            elif self._backend == "gnome-screenshot":
                result = subprocess.run(
                    ["gnome-screenshot", "-f", output_path],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
            elif self._backend == "import":
                result = subprocess.run(
                    ["import", "-window", "root", output_path],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
            else:
                return None

            if result.returncode != 0:
                logger.error(f"Screenshot failed: {result.stderr}")
                return None

            if os.path.isfile(output_path):
                logger.info(f"Screenshot saved: {output_path}")
                return output_path
            else:
                logger.error("Screenshot file not created")
                return None

        except subprocess.TimeoutExpired:
            logger.error("Screenshot timed out")
            return None
        except Exception as e:
            logger.error(f"Screenshot error: {e}")
            return None

    @property
    def backend(self) -> str:
        """Get the current screenshot backend."""
        return self._backend

    @property
    def available(self) -> bool:
        """Check if screenshot capture is available."""
        return self._backend != "none"
