"""Quick end-to-end test of OpenClawPlanner in CecilOs."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cecil_simple import OpenClawPlanner

p = OpenClawPlanner()

print(f"CLI path : {p.cli_path or '(not found)'}")
print(f"Connected: {p.connect()}")

tests = [
    ("abre firefox",                   "firefox"),
    ("abre la terminal kitty",         "kitty"),
    ("cierra la ventana activa",       "close_window"),
    ("escribe hola mundo",             "type"),
]

print()
ok_count = 0
for cmd, expected_hint in tests:
    actions = p.plan(cmd)
    if actions:
        print(f"  ✓  '{cmd}'\n     → {actions}")
        ok_count += 1
    else:
        print(f"  ✗  '{cmd}' — error: {p.last_error}")

print(f"\n{ok_count}/{len(tests)} planes OK")
