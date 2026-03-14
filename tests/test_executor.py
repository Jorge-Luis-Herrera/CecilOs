#!/usr/bin/env python3
"""Quick test for the fixed executor."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cecil_hand.executor import InputExecutor

ex = InputExecutor()
print(f"Backend: {ex.backend}")
print()

tests = ["super", "Return", "Escape", "ctrl+c", "alt+F4", "ctrl+shift+t"]
for t in tests:
    print(f"  {t:20s} -> {ex._resolve_keycodes(t)}")

print()
print("Now testing real key press: Super (should open launcher)")
print("Sending in 3 seconds...")
import time
time.sleep(3)
ok = ex.key("super")
print(f"Result: {'OK' if ok else 'FAILED'}")
time.sleep(2)
ex.key("Escape")
print("Escape sent to close launcher")
