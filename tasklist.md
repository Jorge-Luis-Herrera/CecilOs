# Tasklist de Microservicios: Proyecto CecilOs

Este documento detalla la hoja de ruta técnica para la implementación de los servicios desacoplados que componen el agente cognitivo.

---

## 1. Microservicio: Cecil-Ear (Wake Word Engine)
*Módulo de escucha pasiva de ultra bajo consumo.*

- [X] **Selección de Motor:** Implementar motor KWS (Keyword Spotting).
    - *Opción A:* Porcupine (Picovoice) - Más eficiente.
    - *Opción B:* OpenWakeWord (ONNX Runtime).
- [ ] **Subprogramas:**
    - `AudioCaptureService`: Gestión de flujo de audio por debajo de 16kHz.
    - `TriggerDetector`: Lógica de comparación de patrones fonéticos.
- [ ] **Dependencias:**
    - `androidx.core:core-ktx`
    - `onnxruntime-android` (si se usa OpenWakeWord).
- [ ] **Salida:** Evento `WAKE_UP_BROADCAST`.

---

## 2. Microservicio: Cecil-Listen (STT Engine)
*Conversión de voz a texto tras la activación.*

- [ ] **Core:** Integración de `Whisper.cpp` mediante JNI (C++ nativo en Android).
- [ ] **Subprogramas:**
    - `VAD (Voice Activity Detection)`: Para saber cuándo el usuario deja de hablar.
    - `ModelManager`: Descarga y verificación de modelos cuantizados (4-bit/GGML).
- [ ] **Dependencias:**
    - `whisper-android-sdk`
    - `CMake` (para compilación de libwhisper.so).
- [ ] **Salida:** String de texto `USER_COMMAND`.

---

## 3. Microservicio: Cecil-Vision (Visual Parser)
*El "ojo" del sistema que interpreta la pantalla.*

- [ ] **Implementación OmniParser:**
    - `IconDetector`: Modelo YOLOv8/v10 para detectar elementos interactivos.
    - `Captioner`: Generación de descripción de contexto para elementos sin etiqueta.
- [ ] **Subprogramas:**
    - `ScreenCapturer`: Uso de `MediaProjection` o `Shizuku API` para capturas de alta velocidad.
    - `OCR Engine`: Tesseract o Google ML Kit para leer texto en imágenes.
- [ ] **Dependencias:**
    - `TensorFlow Lite` o `PyTorch Mobile`.
    - `OpenCV Android SDK`.
- [ ] **Salida:** JSON `ScreenLayoutStructure`.

---

## 4. Microservicio: Cecil-Brain (Reasoning & KG-RAG)
*El cerebro que decide qué hacer.*

- [ ] **Gestor de Grafos (UTG):**
    - `GraphSync`: Lógica para actualizar el grafo cuando cambia la versión de una App (`ACTION_PACKAGE_REPLACED`).
    - `PathFinder`: Algoritmo de búsqueda de rutas en el grafo de la aplicación.
- [ ] **Local LLM:**
    - Integración de `Llama.cpp` o `MediaPipe LLM Inference` para procesar el comando vs la estructura de la pantalla.
- [ ] **Dependencias:**
    - `SQLite / Room Persistence`: Para almacenar el grafo de conocimiento.
    - `JGraphT` (Librería de estructuras de datos de grafos).
- [ ] **Salida:** `ActionPlan` (ej: "Hacer click en botón X").

---

## 5. Microservicio: Cecil-Hand (Execution Layer)
*El ejecutor de acciones físicas.*

- [ ] **Interface Shizuku:**
    - `ShizukuProvider`: Conexión de confianza con el proceso root/adb.
    - `GestureInjector`: Simulación de taps, swipes y scrolls.
- [ ] **Subprogramas:**
    - `ActionValidator`: Verifica si la acción se realizó correctamente analizando el nuevo estado de la pantalla.
- [ ] **Dependencias:**
    - `dev.rikka.shizuku:api`
- [ ] **Salida:** Confirmación de ejecución o error.

---

## 6. Microservicio: Supervisor (Lifecycle & Power)
*Coordinador de estados de energía.*

- [ ] **Estados de Energía:**
    - `IdleState`: Solo Cecil-Ear activo.
    - `ActiveState`: Whisper y Vision activados.
- [ ] **Monitor de Apps:**
    - `AppTracker`: Detecta qué app está en primer plano para cargar el grafo correspondiente desde el KG-RAG.
- [ ] **Dependencias:**
    - `WorkManager` (para tareas de mantenimiento de grafos).
- [ ] **Salida:** Gestión de prioridad de CPU (OOM score).

---

## Herramientas de Desarrollo Necesarias
- **IDE:** Android Studio Ladybug+.
- **Lenguaje:** Kotlin 1.9+, C++ (NDK).
- **Control de Versiones:** Git con LFS (para modelos ML pesados).