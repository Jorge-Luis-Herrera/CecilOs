import ctypes
import platform
import os
from pathlib import Path

def debug_load():
    lib_name = ""
    system = platform.system()
    if system == "Darwin":
        lib_name = "libmoonshine.dylib"
    elif system == "Linux":
        lib_name = "libmoonshine.so"
    elif system == "Windows":
        lib_name = "moonshine.dll"
    else:
        print(f"Unsupported platform: {system}")
        return

    print(f"System: {system}")
    print(f"Target library name: {lib_name}")

    # Possible paths based on moonshine_api.py
    # Assuming this script is in Cecil-Ear/moonshine/python/
    base_dir = Path("/home/jorge/Desktop/Home/GitHub/CecilOs/Cecil-Ear/moonshine/python")
    possible_paths = [
        base_dir / "src" / "moonshine_voice" / lib_name,
        base_dir / lib_name,
        base_dir.parent.parent / "core" / "build" / lib_name,
        Path("/usr/local/lib") / lib_name,
        Path("/usr/lib") / lib_name,
    ]

    for path in possible_paths:
        exists = path.exists()
        print(f"Checking {path}: {'EXISTS' if exists else 'not found'}")
        if exists:
            try:
                print(f"Attempting to load {path}...")
                lib = ctypes.CDLL(str(path))
                print(f"SUCCESS: Loaded {path}")
                print(f"Library version: {lib.moonshine_get_version()}")
                return
            except Exception as e:
                print(f"FAILURE loading {path}: {e}")
                # Try to run ldd on it if on Linux
                if system == "Linux":
                    print("Running ldd...")
                    os.system(f"ldd {path}")
    
    # Try loading by name
    try:
        print(f"Attempting to load by name: {lib_name}...")
        lib = ctypes.CDLL(lib_name)
        print(f"SUCCESS: Loaded {lib_name}")
    except Exception as e:
        print(f"FAILURE loading by name: {e}")

if __name__ == "__main__":
    debug_load()
