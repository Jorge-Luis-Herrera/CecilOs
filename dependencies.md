# Guía de Instalación y Dependencias (CecilOs)

Este documento detalla los pasos realizados para configurar el motor de transcripción Moonshine (Ear/Listen) en un sistema CachyOS (basado en Arch).

## 1. Requisitos del Sistema
- **SO**: Linux (probado en CachyOS/Arch/Hyprland)
- **Compilador**: `g++` (v14+)
- **Build System**: `cmake` (v3.25+)
- **Python**: 3.14 (se recomienda usar un entorno virtual para no ensuciar el sistema)

## 2. Configuración del Entorno Python
```bash
python -m venv env
source env/bin/activate
pip install -r Cecil-Ear/moonshine/python/requirements.txt
# Además de las dependencias base, se usó:
pip install onnxruntime-gpu huggingface-hub sounddevice soundfile requests cmake
```

## 3. Compilación del Motor Core (C++)
Moonshine utiliza un núcleo en C++ que debe ser compilado localmente para tu arquitectura:

1. Navega a `Cecil-Ear/moonshine/core/`.
2. Crea una carpeta de construcción: `mkdir build && cd build`.
3. Ejecuta CMake: `cmake .. -DCMAKE_BUILD_TYPE=Release`.
4. Compila: `make -j$(nproc)`.
5. Esto generará `libmoonshine.so`.

**Nota importante**: En el archivo `Cecil-Ear/moonshine/core/speaker-embedding-model-data.cpp`, se "dummyficaron" los vectores de diarización y se ajustó el manejador de errores en `transcriber.cpp` para permitir que el sistema funcione sin los archivos de pesos del modelo de identificación de hablantes (speaker-embedding), los cuales suelen requerir Git LFS.

## 4. Obtención de Modelos (Español)
Para que el sistema funcione sin una conexión constante a la nube, se deben descargar los archivos `.ort` y el `tokenizer.bin`. 

Repositorio sugerido: `UsefulSensors/moonshine-es`.

```bash
mkdir -p Cecil-Ear/moonshine/test-assets/moonshine-es
cd Cecil-Ear/moonshine/test-assets/moonshine-es

# Descarga manual (curl o wget)
curl -L "https://huggingface.co/UsefulSensors/moonshine-es/resolve/main/onnx/merged/base/float/encoder_model.ort?download=true" -o encoder_model.ort
curl -L "https://huggingface.co/UsefulSensors/moonshine-es/resolve/main/onnx/merged/base/float/decoder_model_merged.ort?download=true" -o decoder_model_merged.ort
curl -L "https://huggingface.co/UsefulSensors/moonshine-es/resolve/main/onnx/merged/base/float/tokenizer.bin?download=true" -o tokenizer.bin
```

## 5. Enlace con Python
Para que el paquete Python encuentre la librería C++:

1. Copia `Cecil-Ear/moonshine/core/build/libmoonshine.so` a `Cecil-Ear/moonshine/python/src/moonshine_voice/`.
2. Asegúrate de tener `libonnxruntime.so.1` en el PATH de librerías o en la misma carpeta del paquete.

## 6. Verificación (Jupyter Notebook)
En el archivo `Cecil-Ear/moonshine/python/test.ipynb` puedes ejecutar las celdas para:
1. Validar la importación de `moonshine_voice`.
2. Cargar el modelo en español desde la ruta de `test-assets`.
3. Grabar audio real desde tu micrófono y ver la transcripción en vivo.

---
**Nota de CecilOs**: Mantén los modelos y los entornos virtuales (`env/`, `venv/`) fuera del repositorio Git mediante el archivo `.gitignore` para evitar subir binarios pesados e innecesarios.
