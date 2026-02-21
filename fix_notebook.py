#!/usr/bin/env python3
import json

notebook_path = '/home/jorge/Desktop/Home/GitHub/CecilOs/Cecil-Ear/moonshine/python/test.ipynb'

with open(notebook_path, 'r') as f:
    nb = json.load(f)

# Nueva celda corregida para la grabación con micrófono
new_cell_source = '''import numpy as np
import sounddevice as sd
from scipy import signal

# ============================================
# DETECCIÓN AUTOMÁTICA DE MICRÓFONO
# ============================================
def get_working_microphone():
    """Detecta y devuelve el ID de un micrófono funcional."""
    # Primero intentar el dispositivo por defecto
    try:
        default_dev = sd.query_devices(kind='input')
        devices = sd.query_devices()
        for i, d in enumerate(devices):
            if d['name'] == default_dev['name'] and d['max_input_channels'] > 0:
                print(f"✅ Micrófono detectado: ID {i} - {d['name']}")
                return i
    except Exception as e:
        print(f"⚠️ Error con dispositivo por defecto: {e}")
    
    # Buscar cualquier dispositivo con canales de entrada
    devices = sd.query_devices()
    for i, d in enumerate(devices):
        if d['max_input_channels'] > 0:
            print(f"✅ Micrófono alternativo: ID {i} - {d['name']}")
            return i
    
    # Último recurso: usar None (dispositivo default del sistema)
    print("⚠️ Usando dispositivo por defecto del sistema")
    return None

# Detectar micrófono
DEVICE_ID = get_working_microphone()
print(f"🎤 ID de dispositivo seleccionado: {DEVICE_ID}")

# ============================================
# FUNCIÓN DE TRANSCRIPCIÓN EN VIVO
# ============================================
def transcribe_live_robust(duration=5):
    """Graba del micrófono y transcribe con Moonshine."""
    print(f"\\n--- GRABANDO POR DISPOSITIVO {DEVICE_ID} ---")
    
    sr_target = 16000
    try:
        # Obtener info del dispositivo
        if DEVICE_ID is not None:
            dev_info = sd.query_devices(DEVICE_ID, 'input')
            sr_native = int(dev_info['default_samplerate'])
        else:
            sr_native = 44100  # Default común
        
        print(f"Capturando a {sr_native}Hz...")
        print("🎤 HABLA AHORA...")
        
        recording = sd.rec(
            int(duration * sr_native),
            samplerate=sr_native,
            channels=1,
            dtype='float32',
            device=DEVICE_ID
        )
        sd.wait()
        print("Grabación finalizada.")
        
        # Procesar audio
        audio_data = recording.flatten()
        audio_data = audio_data - np.mean(audio_data)
        
        # Resamplear si es necesario
        if sr_native != sr_target:
            print(f"Resampleando de {sr_native} a {sr_target}...")
            num_samples = int(len(audio_data) * sr_target / sr_native)
            audio_data = signal.resample(audio_data, num_samples)
        
        # Normalizar
        max_amp = np.max(np.abs(audio_data))
        if max_amp > 0:
            audio_data = audio_data / (max_amp + 1e-6) * 0.7
            print(f"Audio normalizado (Amp max: {max_amp:.4f})")
        
        # Transcribir
        print("Llamando al motor Moonshine (C++)...")
        audio_list = audio_data.tolist()
        print(f"Samples a procesar: {len(audio_list)}")
        
        transcript = transcriber.transcribe_without_streaming(audio_list)
        print("Motor C++ respondió con éxito.")
        
        print("-" * 30)
        found = False
        if transcript.lines:
            for line in transcript.lines:
                if line.text.strip():
                    print(f"CECIL ESCUCHÓ: {line.text}")
                    found = True
        
        if not found:
            print("No se detectó voz clara.")
        print("-" * 30)
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

# Ejecutar transcripción
transcribe_live_robust(duration=5)
'''

# Buscar la última celda de código y reemplazarla
last_code_cell_idx = None
for i, cell in enumerate(nb['cells']):
    if cell['cell_type'] == 'code':
        last_code_cell_idx = i

if last_code_cell_idx is not None:
    nb['cells'][last_code_cell_idx]['source'] = new_cell_source.split('\n')
    nb['cells'][last_code_cell_idx]['outputs'] = []
    nb['cells'][last_code_cell_idx]['execution_count'] = None
    print(f"✅ Celda {last_code_cell_idx} reemplazada")

with open(notebook_path, 'w') as f:
    json.dump(nb, f, indent=1)

print(f"✅ Notebook guardado: {notebook_path}")
