#!/usr/bin/env python3
"""Debug CecilOs startup."""
import sys, os, traceback
sys.path.insert(0, '/home/jorge/Desktop/Home/GitHub/CecilOs')
sys.path.insert(0, '/home/jorge/Desktop/Home/GitHub/CecilOs/Cecil-Ear/moonshine/python/src')

try:
    print("1. Importing modules...")
    from cecil_hand.executor import InputExecutor
    from cecil_brain.intent_parser import parse as parse_intent
    from cecil_vision.capture import ScreenCapture
    from cecil_vision.parser import ScreenParser
    print("   All imports OK")

    print("2. Creating ScreenCapture...")
    sc = ScreenCapture()
    print(f"   Backend: {sc._backend}")

    print("3. Creating ScreenParser...")
    sp = ScreenParser()
    print(f"   AT-SPI2: {sp._has_atspi}, Tesseract: {sp._has_tesseract}")

    print("4. Creating LocalBrain...")
    from cecil_simple import LocalBrain
    lb = LocalBrain()
    print(f"   Model: {lb._model_path}, Available: {lb.available}")

    print("5. Launching GUI...")
    import tkinter as tk
    from cecil_simple import CecilApp
    root = tk.Tk()
    app = CecilApp(root)
    print("   GUI created successfully, entering mainloop")
    root.mainloop()

except Exception as e:
    print(f"ERROR: {e}")
    traceback.print_exc()
