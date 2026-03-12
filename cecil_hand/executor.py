"""
Cecil-Hand Executor.

Translates ActionStep commands into system-level input events
using ydotool (Wayland-compatible) on Linux.

Fallback chain: ydotool → xdotool → error
"""

import logging
import os
import shutil
import subprocess
import time
from typing import Optional

logger = logging.getLogger("cecil.hand")

# ydotool v1.x uses raw Linux keycodes from input-event-codes.h
# See: /usr/include/linux/input-event-codes.h
_KEYCODE_MAP = {
    # Modifiers
    "super": 125, "leftmeta": 125, "meta": 125,
    "ctrl": 29, "leftctrl": 29, "control": 29,
    "shift": 42, "leftshift": 42,
    "alt": 56, "leftalt": 56,
    "rightctrl": 97, "rightalt": 100, "rightshift": 54,
    # Common keys
    "return": 28, "enter": 28, "kpenter": 96,
    "escape": 1, "esc": 1,
    "tab": 15,
    "space": 57,
    "backspace": 14,
    "delete": 111,
    "home": 102, "end": 107,
    "pageup": 104, "pagedown": 109,
    "up": 103, "down": 108, "left": 105, "right": 106,
    "capslock": 58,
    "print": 210, "sysrq": 99,
    "insert": 110,
    "volumeup": 115, "volumedown": 114, "mute": 113,
    # F-keys
    "f1": 59, "f2": 60, "f3": 61, "f4": 62, "f5": 63, "f6": 64,
    "f7": 65, "f8": 66, "f9": 67, "f10": 68, "f11": 87, "f12": 88,
    # Letters (QWERTY layout)
    "q": 16, "w": 17, "e": 18, "r": 19, "t": 20, "y": 21, "u": 22,
    "i": 23, "o": 24, "p": 25, "a": 30, "s": 31, "d": 32, "f": 33,
    "g": 34, "h": 35, "j": 36, "k": 37, "l": 38, "z": 44, "x": 45,
    "c": 46, "v": 47, "b": 48, "n": 49, "m": 50,
    # Numbers
    "1": 2, "2": 3, "3": 4, "4": 5, "5": 6,
    "6": 7, "7": 8, "8": 9, "9": 10, "0": 11,
    # Symbols
    "minus": 12, "equal": 13, "bracketleft": 26, "bracketright": 27,
    "semicolon": 39, "apostrophe": 40, "grave": 41,
    "backslash": 43, "comma": 51, "period": 52, "slash": 53,
}


class InputExecutor:
    """
    Executes input actions (tap, type, key, swipe, wait) on the desktop.

    Uses ydotool for Wayland (Hyprland, Sway, etc.) or xdotool for X11.
    """

    def __init__(self):
        self._backend = self._detect_backend()
        logger.info(f"Input executor using backend: {self._backend}")

    def _detect_backend(self) -> str:
        """Detect available input backend."""
        # Check for ydotool first (Wayland)
        if shutil.which("ydotool"):
            # Verify ydotoold is running
            try:
                result = subprocess.run(
                    ["pgrep", "-x", "ydotoold"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    return "ydotool"
                else:
                    logger.warning(
                        "ydotool found but ydotoold daemon is not running. "
                        "Start it with: sudo ydotoold &"
                    )
            except Exception:
                pass

        # Check for xdotool (X11)
        if shutil.which("xdotool"):
            return "xdotool"

        logger.error(
            "No input backend found. Install ydotool (Wayland) or xdotool (X11)."
        )
        return "none"

    def tap(self, x: int, y: int) -> bool:
        """
        Simulate a tap/click at coordinates (x, y).

        Args:
            x: X coordinate.
            y: Y coordinate.

        Returns:
            True if successful.
        """
        logger.info(f"TAP at ({x}, {y})")
        if self._backend == "ydotool":
            return self._run_commands([
                ["ydotool", "mousemove", "--absolute", "-x", str(x), "-y", str(y)],
                ["ydotool", "click", "0x00"],  # Left click (0x00=LEFT)
            ])
        elif self._backend == "xdotool":
            return self._run_command(
                ["xdotool", "mousemove", str(x), str(y), "click", "1"]
            )
        else:
            logger.error("No input backend available for tap")
            return False

    def type_text(self, text: str, target_class: str = "") -> bool:
        """
        Simulate typing text into the focused window.
        If target_class is given, focus that window first.

        Args:
            text: The text to type.
            target_class: Optional window class to focus first (e.g. "kitty", "firefox").

        Returns:
            True if successful.
        """
        if target_class:
            self.focus_window(target_class)
            time.sleep(0.3)

        logger.info(f"TYPE: '{text[:50]}{'...' if len(text) > 50 else ''}'")
        # Prefer wtype on Wayland (handles unicode/locale correctly)
        if shutil.which("wtype"):
            return self._run_command(["wtype", text])
        elif self._backend == "ydotool":
            return self._run_command(
                ["ydotool", "type", "--key-delay", "30", "--", text]
            )
        elif self._backend == "xdotool":
            return self._run_command(["xdotool", "type", "--clearmodifiers", text])
        else:
            logger.error("No input backend available for type")
            return False

    def _resolve_keycodes(self, key_combo: str) -> str:
        """
        Translate a human-readable key combo to ydotool keycode sequence.

        Examples:
            'super'     -> '125:1 125:0'
            'ctrl+c'    -> '29:1 46:1 46:0 29:0'
            'Return'    -> '28:1 28:0'
            'alt+F4'    -> '56:1 62:1 62:0 56:0'
        """
        parts = [p.strip() for p in key_combo.split("+")]
        codes = []
        for part in parts:
            code = _KEYCODE_MAP.get(part.lower())
            if code is None:
                # Try as raw number
                try:
                    code = int(part)
                except ValueError:
                    logger.warning(f"Unknown key: '{part}' — skipping")
                    continue
            codes.append(code)

        if not codes:
            return ""

        # Build sequence: press all modifiers, press+release last key, release modifiers
        sequence = []
        modifiers = codes[:-1]  # all but last are modifiers
        main_key = codes[-1]    # last is the main key

        # If single key, just press and release
        if len(codes) == 1:
            return f"{main_key}:1 {main_key}:0"

        # Press modifiers down
        for mod in modifiers:
            sequence.append(f"{mod}:1")
        # Press and release main key
        sequence.append(f"{main_key}:1")
        sequence.append(f"{main_key}:0")
        # Release modifiers in reverse
        for mod in reversed(modifiers):
            sequence.append(f"{mod}:0")

        return " ".join(sequence)

    def key(self, key_combo: str) -> bool:
        """
        Simulate a key press combination.

        Args:
            key_combo: Key combination (e.g., "super", "ctrl+c", "Return").

        Returns:
            True if successful.
        """
        logger.info(f"KEY: '{key_combo}'")
        if self._backend == "ydotool":
            keycode_seq = self._resolve_keycodes(key_combo)
            if not keycode_seq:
                logger.error(f"Could not resolve key combo: '{key_combo}'")
                return False
            logger.debug(f"Keycodes: {keycode_seq}")
            return self._run_command(
                ["ydotool", "key"] + keycode_seq.split()
            )
        elif self._backend == "xdotool":
            return self._run_command(["xdotool", "key", key_combo])
        else:
            logger.error("No input backend available for key")
            return False

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration: float = 0.3) -> bool:
        """
        Simulate a swipe gesture from (x1,y1) to (x2,y2).

        Args:
            x1, y1: Start coordinates.
            x2, y2: End coordinates.
            duration: Duration of the swipe in seconds.

        Returns:
            True if successful.
        """
        logger.info(f"SWIPE from ({x1},{y1}) to ({x2},{y2})")
        if self._backend == "ydotool":
            steps = 10
            dx = (x2 - x1) / steps
            dy = (y2 - y1) / steps
            step_delay = duration / steps

            # Move to start
            success = self._run_command(
                ["ydotool", "mousemove", "--absolute", "-x", str(x1), "-y", str(y1)]
            )
            if not success:
                return False

            # Mouse down
            success = self._run_command(["ydotool", "mousedown", "0"])
            if not success:
                return False

            # Move in steps
            for i in range(1, steps + 1):
                cx = int(x1 + dx * i)
                cy = int(y1 + dy * i)
                self._run_command(
                    ["ydotool", "mousemove", "--absolute", "-x", str(cx), "-y", str(cy)]
                )
                time.sleep(step_delay)

            # Mouse up
            return self._run_command(["ydotool", "mouseup", "0"])

        elif self._backend == "xdotool":
            # xdotool doesn't have native swipe, simulate with mousemove + click
            success = self._run_command(
                ["xdotool", "mousemove", str(x1), str(y1), "mousedown", "1"]
            )
            if not success:
                return False
            time.sleep(duration)
            return self._run_command(
                ["xdotool", "mousemove", str(x2), str(y2), "mouseup", "1"]
            )
        else:
            logger.error("No input backend available for swipe")
            return False

    def wait(self, seconds: float) -> bool:
        """
        Wait for a specified number of seconds.

        Args:
            seconds: Number of seconds to wait.

        Returns:
            Always True.
        """
        logger.info(f"WAIT: {seconds}s")
        time.sleep(seconds)
        return True

    def _run_command(self, cmd: list) -> bool:
        """Run a single shell command."""
        # Ensure YDOTOOL_SOCKET is set for user daemon compatibility
        env = os.environ.copy()
        if "YDOTOOL_SOCKET" not in env:
            uid = os.getuid()
            env["YDOTOOL_SOCKET"] = f"/run/user/{uid}/.ydotool_socket"

        try:
            result = subprocess.run(
                cmd,
                env=env,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                logger.error(f"Command failed: {' '.join(cmd)}: {result.stderr}")
                return False
            return True
        except subprocess.TimeoutExpired:
            logger.error(f"Command timed out: {' '.join(cmd)}")
            return False
        except Exception as e:
            logger.error(f"Command error: {' '.join(cmd)}: {e}")
            return False

    def _run_commands(self, commands: list) -> bool:
        """Run multiple commands in sequence."""
        for cmd in commands:
            if not self._run_command(cmd):
                return False
            time.sleep(0.05)  # Small delay between commands
        return True

    @property
    def backend(self) -> str:
        """Get the current input backend name."""
        return self._backend

    @property
    def available(self) -> bool:
        """Check if an input backend is available."""
        return self._backend != "none"

    # ── High-level actions (Hyprland-native) ──────────────

    def launch_app(self, app_name: str) -> bool:
        """
        Launch an application directly via hyprctl dispatch exec.
        Much more reliable than simulating keyboard to open launcher.
        Waits briefly and then focuses the new window.

        Args:
            app_name: The executable name (firefox, kitty, nautilus, code, etc.)

        Returns:
            True if successful.
        """
        logger.info(f"LAUNCH APP: '{app_name}'")
        result = self._run_command(
            ["hyprctl", "dispatch", "exec", f"[workspace current] {app_name}"]
        )
        if result:
            # Give the app time to spawn its window, retry focus
            for attempt in range(3):
                time.sleep(1.0)
                if self.focus_window(app_name):
                    break
                logger.info(f"Retry focus {attempt+1}/3 for '{app_name}'...")
        return result

    def open_launcher(self) -> bool:
        """
        Open the application launcher (Rofi/Walker).
        Uses the ML4W launcher script directly.

        Returns:
            True if successful.
        """
        logger.info("OPEN LAUNCHER (rofi)")
        launcher_script = os.path.expanduser("~/.config/hypr/scripts/launcher.sh")
        if os.path.isfile(launcher_script):
            return self._run_command(["bash", launcher_script])
        # Fallback: try rofi directly
        return self._run_command(["rofi", "-show", "drun", "-replace", "-i"])

    def close_window(self) -> bool:
        """Close the active window via hyprctl."""
        logger.info("CLOSE WINDOW (hyprctl)")
        return self._run_command(["hyprctl", "dispatch", "killactive"])

    def minimize_window(self) -> bool:
        """Minimize the active window."""
        logger.info("MINIMIZE WINDOW")
        return self._run_command(
            ["hyprctl", "dispatch", "movetoworkspacesilent", "special"]
        )

    def maximize_window(self) -> bool:
        """Toggle maximize on the active window (keeps waybar visible)."""
        logger.info("MAXIMIZE WINDOW (fullscreen 1)")
        return self._run_command(
            ["hyprctl", "dispatch", "fullscreen", "1"]
        )

    def fullscreen_window(self) -> bool:
        """Toggle true fullscreen on the active window (hides waybar)."""
        logger.info("FULLSCREEN WINDOW (fullscreen 0)")
        return self._run_command(
            ["hyprctl", "dispatch", "fullscreen", "0"]
        )

    def switch_workspace(self, workspace: int) -> bool:
        """Switch to a specific workspace."""
        logger.info(f"SWITCH WORKSPACE: {workspace}")
        return self._run_command(
            ["hyprctl", "dispatch", "workspace", str(workspace)]
        )

    def open_path(self, path: str) -> bool:
        """Open a file or directory with the default handler (non-blocking)."""
        logger.info(f"OPEN PATH: '{path}'")
        expanded = os.path.expanduser(path)
        try:
            subprocess.Popen(
                ["xdg-open", expanded],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True
        except Exception as e:
            logger.error(f"open_path error: {e}")
            return False

    # ── Additional input actions ──────────────────────────

    def scroll(self, x: int, y: int, direction: str = "down", clicks: int = 3) -> bool:
        """
        Scroll at a position. Moves mouse to (x,y) then scrolls.

        Args:
            x, y: Position to scroll at.
            direction: "up" or "down".
            clicks: Number of scroll clicks (each ~3 lines).

        Returns:
            True if successful.
        """
        logger.info(f"SCROLL {direction} x{clicks} at ({x},{y})")
        # Move mouse to position first
        self._run_command(
            ["ydotool", "mousemove", "--absolute", "-x", str(x), "-y", str(y)]
        )
        time.sleep(0.05)
        # ydotool mouse wheel: button 4 = up, button 5 = down
        # Using mousemove with wheel simulation
        for _ in range(clicks):
            if direction == "up":
                self._run_command(["ydotool", "click", "0x00040001"])  # wheel up
            else:
                self._run_command(["ydotool", "click", "0x00050001"])  # wheel down
            time.sleep(0.02)
        return True

    def right_click(self, x: int, y: int) -> bool:
        """Right-click at coordinates (x, y)."""
        logger.info(f"RIGHT CLICK at ({x},{y})")
        if self._backend == "ydotool":
            return self._run_commands([
                ["ydotool", "mousemove", "--absolute", "-x", str(x), "-y", str(y)],
                ["ydotool", "click", "0x01"],  # Right click
            ])
        elif self._backend == "xdotool":
            return self._run_command(
                ["xdotool", "mousemove", str(x), str(y), "click", "3"]
            )
        return False

    def double_click(self, x: int, y: int) -> bool:
        """Double-click at coordinates (x, y)."""
        logger.info(f"DOUBLE CLICK at ({x},{y})")
        if self._backend == "ydotool":
            return self._run_commands([
                ["ydotool", "mousemove", "--absolute", "-x", str(x), "-y", str(y)],
                ["ydotool", "click", "0x00"],
                ["ydotool", "click", "0x00"],
            ])
        elif self._backend == "xdotool":
            return self._run_command(
                ["xdotool", "mousemove", str(x), str(y), "click", "--repeat", "2", "1"]
            )
        return False

    def hover(self, x: int, y: int) -> bool:
        """Move mouse to (x, y) without clicking."""
        logger.info(f"HOVER at ({x},{y})")
        if self._backend == "ydotool":
            return self._run_command(
                ["ydotool", "mousemove", "--absolute", "-x", str(x), "-y", str(y)]
            )
        elif self._backend == "xdotool":
            return self._run_command(["xdotool", "mousemove", str(x), str(y)])
        return False

    def focus_window(self, window_class: str) -> bool:
        """
        Focus a window by its class name using hyprctl.
        E.g. focus_window("kitty") focuses the most recent kitty window.

        Args:
            window_class: The window class (e.g. "kitty", "firefox", "nautilus").

        Returns:
            True if the window was found and focused.
        """
        logger.info(f"FOCUS WINDOW: '{window_class}'")
        try:
            import json as _json
            result = subprocess.run(
                ["hyprctl", "clients", "-j"],
                capture_output=True, text=True, timeout=5,
            )
            clients = _json.loads(result.stdout)
            # Find the best match by class name (case-insensitive)
            target = None
            for c in clients:
                if window_class.lower() in c.get("class", "").lower():
                    if target is None or c.get("focusHistoryID", 999) < target.get("focusHistoryID", 999):
                        target = c
            if target:
                addr = target.get("address", "")
                return self._run_command(
                    ["hyprctl", "dispatch", "focuswindow", f"address:{addr}"]
                )
            else:
                logger.warning(f"No window found with class '{window_class}'")
                return False
        except Exception as e:
            logger.error(f"focus_window error: {e}")
            return False

    def get_active_window(self) -> dict:
        """Get info about the currently focused window."""
        try:
            import json as _json
            result = subprocess.run(
                ["hyprctl", "activewindow", "-j"],
                capture_output=True, text=True, timeout=5,
            )
            return _json.loads(result.stdout)
        except Exception:
            return {}

    def list_windows(self) -> list:
        """List all open windows with their class, title and workspace."""
        try:
            import json as _json
            result = subprocess.run(
                ["hyprctl", "clients", "-j"],
                capture_output=True, text=True, timeout=5,
            )
            return _json.loads(result.stdout)
        except Exception:
            return []
