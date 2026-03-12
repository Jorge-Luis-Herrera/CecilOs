#!/usr/bin/env python3
"""Quick test: open kitty → focus → close"""
import time, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cecil_hand.executor import InputExecutor

e = InputExecutor()

print("Paso 1: Abriendo Kitty...")
e.launch_app("kitty")
time.sleep(3)

print("Paso 2: Enfocando Kitty...")
e.focus_window("kitty")
time.sleep(1)

print("Paso 3: Cerrando con close_window()...")
r = e.close_window()
print(f"Resultado: {r}")
