#!/usr/bin/env python3
import subprocess
import tkinter as tk
import sys
import os

def get_current_layout():
    """Gets the current keyboard layout name from hyprctl."""
    try:
        # Get JSON output from hyprctl
        import json
        result = subprocess.run(["hyprctl", "getoption", "input:kb_layout", "-j"], capture_output=True, text=True)
        # That's layout configuration, not current state. 
        # Current state is in 'hyprctl devices -j'
        result = subprocess.run(["hyprctl", "devices", "-j"], capture_output=True, text=True)
        data = json.loads(result.stdout)
        
        # Look for keyboard with layout
        for k in data.get("keyboards", []):
            if k.get("main", False):
                return k.get("active_keymap", "??")
        
        # Fallback if no main keyboard
        if data.get("keyboards"):
            return data["keyboards"][0].get("active_keymap", "??")
    except Exception as e:
        print(f"Error getting layout: {e}")
    return "??"

def show_osd(layout_name):
    """Shows a small, centered OSD animation with the layout name."""
    root = tk.Tk()
    root.overrideredirect(True)  # No window decorations
    root.attributes("-topmost", True)
    root.wait_visibility(root)
    root.attributes("-alpha", 0.0) # Start invisible
    
    # Appearance
    bg_color = "#1e1e2e" # Catppuccin Mocha
    fg_color = "#cdd6f4"
    accent_color = "#89dceb" # Sky
    
    root.configure(bg=bg_color, highlightbackground=accent_color, highlightthickness=1)
    
    label = tk.Label(root, text=f"⌨ {layout_name}", font=("Cantarell", 12, "bold"),
                    bg=bg_color, fg=fg_color, padx=15, pady=5)
    label.pack()
    
    # Position: Bottom Left
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    width = label.winfo_reqwidth()
    height = label.winfo_reqheight()
    x = 20 # 20px from left
    y = screen_height - height - 80 # 80px from bottom (usually above a bottom bar)
    root.geometry(f"{width}x{height}+{x}+{y}")
    
    # Simple animation: fade in, wait, fade out
    def fade_in():
        alpha = root.attributes("-alpha")
        if alpha < 0.9:
            root.attributes("-alpha", alpha + 0.1)
            root.after(20, fade_in)
        else:
            root.after(800, fade_out)

    def fade_out():
        alpha = root.attributes("-alpha")
        if alpha > 0.0:
            root.attributes("-alpha", alpha - 0.1)
            root.after(20, fade_out)
        else:
            root.destroy()
            sys.exit(0)

    fade_in()
    root.mainloop()

if __name__ == "__main__":
    # 1. Switch layout
    subprocess.run(["hyprctl", "switchxkblayout", "all", "next"])
    
    # 2. Give it a tiny moment to update
    import time
    time.sleep(0.05)
    
    # 3. Get layout and show OSD
    layout = get_current_layout()
    show_osd(layout)
