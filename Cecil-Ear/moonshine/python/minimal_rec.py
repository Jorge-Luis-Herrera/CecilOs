import sys
import os
import numpy as np
import sounddevice as sd
from scipy import signal

# Asegurar que encuentre la librería local
sys.path.insert(0, os.path.abspath('src'))
from moonshine_voice import Transcriber, ModelArch

def record_and_transcribe(duration=5, device_id=4):
    model_path = '../test-assets/moonshine-es'
    
    # 1. Cargar Motor
    engine = Transcriber(model_path=model_path, model_arch=ModelArch.BASE)
    
    # 2. Captura Robusta (48kHz -> 16kHz)
    sr_native = int(sd.query_devices(device_id, 'input')['default_samplerate'])
    print(f"--- ESCUCHANDO ({duration}s) ---")
    
    audio = sd.rec(int(duration * sr_native), samplerate=sr_native, channels=1, dtype='float32', device=device_id)
    sd.wait()
    
    # 3. Procesamiento rápido
    audio = audio.flatten()
    if sr_native != 16000:
        audio = signal.resample(audio, int(len(audio) * 16000 / sr_native))
    
    # 4. Salida a consola
    result = engine.transcribe_without_streaming(audio)
    print("\nRESULTADO:")
    for line in result.lines:
        if line.text.strip():
            print(f"> {line.text}")

if __name__ == "__main__":
    try:
        record_and_transcribe()
    except Exception as e:
        print(f"Error: {e}")
