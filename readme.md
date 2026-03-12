# 🤖 CecilOs — Asistente Autónomo de Escritorio

**CecilOs** es un agente de escritorio controlado por voz y texto que opera **100% local** sobre **Linux Wayland (Hyprland)**. Sin APIs en la nube, sin telemetría, sin dependencias externas en tiempo de ejecución.

Combina reconocimiento de voz (Moonshine STT), síntesis de voz (Piper TTS), un LLM local (Qwen 2.5 via llama-cpp-python), visión de pantalla (AT-SPI2 + Tesseract OCR), y control de input (ydotool) para ejecutar tareas complejas en el sistema operativo a partir de comandos en lenguaje natural.

---

## 🏗️ Arquitectura — Pipeline de 3 Capas

```
Comando del usuario (voz o texto)
         │
         ▼
┌─────────────────────────────────────┐
│  Layer 1: Intent Parser             │  ← Instant, regex/diccionario
│  "abre firefox" → OPEN_APP firefox  │     0ms, 0 GPU
└──────────────┬──────────────────────┘
               │ no reconocido
               ▼
┌─────────────────────────────────────┐
│  Layer 2: LLM Plan (sin visión)     │  ← Qwen 2.5 1.5B, keybindings
│  Genera árbol de acciones atómicas  │     ~2-5s, GPU
└──────────────┬──────────────────────┘
               │ plan vacío o falló
               ▼
┌─────────────────────────────────────┐
│  Layer 3: Vision + LLM + Keys      │  ← PRA Loop (Perceive-Reason-Act)
│  Captura pantalla → AT-SPI2/OCR    │     Coordenadas + keybindings
│  → LLM genera plan → ejecuta       │     Re-intenta hasta 3 veces
└─────────────────────────────────────┘
```

### Modos de operación

| Modo | Cómo funciona |
|------|---------------|
| **GUI manual** | Escribe un comando en el input → click "Ejecutar" |
| **Push-to-talk** | Click 🎙️ → graba → transcribe → llena el input |
| **Always-on** | "Hola Cecil" → escucha comando → ejecuta → responde con voz |

- En modo always-on, di **"Detente"** para cancelar la acción en curso
- El VAD (Voice Activity Detection) de Moonshine segmenta automáticamente por silencios

---

## 📁 Estructura de Módulos

```
CecilOs/
├── cecil_simple.py          # App principal (GUI tkinter + pipeline 3 capas)
│
├── cecil_brain/             # 🧠 Cerebro
│   ├── intent_parser.py     # L1: Parser regex/diccionario (23 intents)
│   ├── keybindings.py       # Atajos de teclado (Hyprland + apps: 104 bindings)
│   ├── llm_engine.py        # L2/L3: Motor LLM (llama-cpp-python + Qwen)
│   ├── task_cache.py        # Cache de planes exitosos (ChromaDB/JSON fallback)
│   └── service.py           # Event bus service (para arquitectura pub/sub)
│
├── cecil_hand/              # 🤚 Ejecutor de acciones
│   ├── executor.py          # Control de input: ydotool/wtype (clicks, teclas, texto)
│   └── service.py           # Event bus service
│
├── cecil_vision/            # 👁️ Visión de pantalla
│   ├── capture.py           # Captura de pantalla (grim en Wayland)
│   ├── parser.py            # Parser: AT-SPI2 (accesibilidad) + Tesseract OCR
│   └── service.py           # Event bus service
│
├── cecil_voice/             # 🗣️ Voz
│   └── tts.py               # Text-to-Speech (Piper TTS, es_MX, CPU)
│
├── Cecil-Ear/               # 👂 STT Engine (Moonshine, subproyecto C++/Python)
│   └── moonshine/           # Fork de Moonshine con modelo español
│
├── cecil_core/              # 🔧 Núcleo
│   ├── event_bus.py         # Bus de eventos pub/sub
│   └── events.py            # Definiciones de eventos
│
├── models/
│   └── tts/
│       ├── es_MX-claude-high.onnx       # Modelo TTS (63MB, gitignored)
│       └── es_MX-claude-high.onnx.json  # Config del modelo TTS
│
└── test_*.py                # Suite de tests interactivos
```

---

## 🛠️ Dependencias del Sistema

### Sistema operativo
- **Linux** con **Wayland** (probado en CachyOS + Hyprland 0.54.1)
- Kernel 6.19.6+

### Herramientas del sistema
| Herramienta | Propósito | Instalación (Arch) |
|-------------|-----------|-------------------|
| `ydotool` + `ydotoold` | Control de mouse/teclado (Wayland) | `sudo pacman -S ydotool` |
| `wtype` | Escritura de texto (Wayland) | `sudo pacman -S wtype` |
| `grim` | Captura de pantalla (Wayland) | `sudo pacman -S grim` |
| `tesseract` | OCR fallback | `sudo pacman -S tesseract tesseract-data-spa tesseract-data-eng` |
| `espeak-ng` | Phonemizer para Piper TTS | `sudo pacman -S espeak-ng` |

### Python (3.14+)
```
llama-cpp-python    # Motor LLM (GPU CUDA)
piper-tts           # Text-to-Speech local
sounddevice         # Audio I/O
numpy               # Audio processing
PyGObject           # AT-SPI2 bindings
```

### Modelos (no incluidos en el repo)
| Modelo | Tamaño | Ubicación |
|--------|--------|-----------|
| Qwen 2.5 1.5B GGUF | 1.1 GB | `~/qwen2.5-1.5b.gguf` |
| Moonshine ES (BASE) | ~50 MB | `Cecil-Ear/moonshine/test-assets/moonshine-es/` |
| Piper es_MX-claude-high | 63 MB | `models/tts/es_MX-claude-high.onnx` |

---

## 🚀 Ejecución

```bash
# 1. Activar entorno virtual
source .venv/bin/activate

# 2. Asegurar que ydotoold está corriendo
systemctl --user start ydotoold

# 3. Ejecutar
python cecil_simple.py
```

---

## 🧪 Tests

```bash
python test_system.py          # Suite completa (interactiva)
python test_system.py capture  # Solo captura de pantalla
python test_system.py vision   # Solo visión (AT-SPI2 + OCR)
python test_system.py hand     # Solo control de input
python test_system.py brain    # Solo motor LLM
python test_actions.py         # Tests individuales de cada acción
python test_imports.py         # Verificar imports
```

---

## 📄 Licencia

Proyecto personal. Todos los derechos reservados por ahora.

---

## 🗺️ Roadmap → v1.0

La rama `v-1.0` implementará el siguiente cambio de arquitectura:

- **Skill Cache semántico**: Cachear planes exitosos como intenciones semánticas (no coordenadas), reutilizarlos automáticamente
- **Resolución de coordenadas en runtime**: Los planes guardan "click botón 'Compile'", y en ejecución se resuelve la posición real vía AT-SPI2/OCR
- **Rolling semanal de validación**: Verificar semanalmente que los planes cacheados siguen funcionando
- **Agente autónomo**: Descomponer tareas complejas en árboles de decisión de acciones atómicas
