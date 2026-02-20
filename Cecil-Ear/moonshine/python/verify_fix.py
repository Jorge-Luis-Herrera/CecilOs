import os
import sys

# Ensure we can import from the source directory
sys.path.append(os.path.join(os.getcwd(), 'src'))

try:
    print("Attempting to import moonshine_voice...")
    import moonshine_voice
    print("SUCCESS: Imported moonshine_voice")
except ImportError as e:
    print(f"FAILURE: Could not import moonshine_voice: {e}")
    sys.exit(1)

try:
    print("Attempting to get model for language 'es'...")
    # This will check for local models or download them to cache
    model_path, model_arch = moonshine_voice.get_model_for_language("es")
    print(f"SUCCESS: Got model path: {model_path}")
    print(f"Model Arch: {model_arch}")
except Exception as e:
    print(f"FAILURE: Could not get model: {e}")
    sys.exit(1)

try:
    print("Attempting to initialize Transcriber...")
    transcriber = moonshine_voice.Transcriber(model_path=model_path, model_arch=model_arch)
    print("SUCCESS: Transcriber initialized")
except Exception as e:
    print(f"FAILURE: Could not initialize Transcriber: {e}")
    # Print the full traceback to see the underlying error if it persists
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\nVerification PASSED: Library loaded and Transcriber initialized successfully.")
