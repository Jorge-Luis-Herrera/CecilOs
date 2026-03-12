"""
Root conftest.py — ensures the project root is in sys.path
so that tests in tests/ can import project modules directly.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
