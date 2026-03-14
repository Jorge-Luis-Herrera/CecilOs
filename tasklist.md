# 🗺️ CecilOs v1.0 — Roadmap: Agente Autónomo con Skill Cache

> **Rama**: `v-1.0`
> **Base**: `master` (pipeline 3 capas funcional con voz)
> **Objetivo**: Transformar CecilOs de un asistente reactivo (1 comando → 1 ejecución)
> a un **agente autónomo** que descompone tareas complejas, cachea planes exitosos,
> y reutiliza experiencia sin re-planificar.

---

## 🧩 Principios de Diseño

### 1. Separación Decisión vs Acción
- **Decisiones** (largo plazo): Se cachean como intenciones semánticas
  - ✅ `"click botón 'Compile'"` — semántico, sobrevive cambios de UI
  - ❌ `"click (450, 320)"` — frágil, se rompe si cambia la fuente/tema
- **Acciones** (momento): Se resuelven en runtime
  - Captura de pantalla → AT-SPI2/OCR → resolver coordenadas actuales
  - Nunca se cachean coordenadas ni screenshots

### 2. Composicionalidad
- Tareas complejas se descomponen en sub-tareas reutilizables
- `"créame y compílame un hola mundo en Rust"` →
  1. `abrir_terminal` (skill cacheada)
  2. `crear_archivo("main.rs", contenido)` (skill cacheada)
  3. `ejecutar_comando("rustc main.rs")` (skill cacheada)
- Cada sub-skill se cachea independientemente

### 3. Validación Rolling
- Cada semana, verificar 1-a-1 si los planes cacheados siguen funcionando
- Si falla el paso N → re-planificar desde el paso N
- Sin crashear RAM: validación secuencial, un plan a la vez

---

## 📋 Tareas de Implementación

### Fase 1: Skill Cache (semántico) ✅ COMPLETADA
- [x] **1.1** Diseñar schema del Skill Cache
  - ✅ Campos: `command_embedding`, `semantic_steps[]`, `app_context`, `success_count`, `last_validated`, `created_at`
  - ✅ Cada step: `{intent: "click_button", target_label: "Compile", fallback_key: "F5"}`
  - ✅ Sin coordenadas, sin screenshots
- [x] **1.2** Implementar `cecil_brain/skill_cache.py`
  - ✅ Búsqueda por keyword (embeddings TODO en Fase 5)
  - ✅ CRUD: save, query, invalidate, list
  - ✅ Backend: SQLite + JSON fallback
- [x] **1.3** Integrar Skill Cache en el pipeline
  - ✅ Nuevo Layer 0.5: antes de L1, consultar cache
  - ✅ Si hay hit con confianza >0.85 → ejecutar plan cacheado directamente
  - ✅ Si falla en paso N → caer a L2/L3 para re-planificar desde paso N

### Fase 2: Resolver de Coordenadas (AT-SPI2 + OCR) ✅ COMPLETADA
- [x] **2.1** Diseñar estrategia resolver
  - ✅ AT-SPI2 primario (90% confiabilidad, <100ms)
  - ✅ OCR fallback (40-60% confiabilidad, universal)
  - ✅ Cache de 15s con TTL automático
- [x] **2.2** Implementar `cecil_brain/resolver.py`
  - ✅ AT_SPI2Resolver: acceso a árbol de accesibilidad Linux
  - ✅ Fuzzy matching con distancia Levenshtein ≤ 2
  - ✅ Confidence scoring (0.99 exacto, 0.95 substring, 0.80+ fuzzy)
  - ✅ OCRResolver: fallback con Tesseract
  - ✅ UIResolver: interfaz principal con cascada AT-SPI2 → OCR
- [x] **2.3** Integrar resolver en pipeline
  - ✅ SemanticStep(intent="click_button", target="Compile")
  - ✅ Resuelve "Compile" → (452, 318) en tiempo de ejecución
  - ✅ Click en coordenadas resueltas
  - ✅ Fallback a fallback_key si resolver falla

### Fase 2: Resolución semántica en runtime
- [ ] **2.1** Crear `cecil_vision/resolver.py`
  - Input: `{intent: "click_button", target_label: "Compile"}`
  - Output: `{type: "tap", x: 452, y: 318}` (coordenadas actuales)
  - Usa AT-SPI2 primero (buscar elemento por label/role)
  - Fallback OCR: buscar texto "Compile" en screenshot

### Fase 3: Descomposición de tareas complejas (PRÓXIMA)
- [ ] **3.1** Implementar `cecil_brain/decomposer.py`
  - Input: comando complejo ("créame y compílame un hola mundo en Rust")
  - Output: lista de sub-tareas atómicas
  - Usa LLM para descomponer, verifica que cada sub-tarea es skill conocida o acción atómica
- [ ] **3.2** Composición de skills
  - Las sub-tareas pueden ser skills cacheadas o acciones nuevas
  - Si una sub-tarea tiene skill cacheada → usarla
  - Si no → planificar con L2/L3 y cachear el resultado
- [ ] **3.3** Integración en pipeline
  - L0.5 → Si cache hit DIRECTO → ejecutar
  - L0.5 → Si cache hit PARCIAL o MISS → descomponer → L1-L3

### Fase 4: Validación y mantenimiento (FUTURO)
- [ ] **4.1** Rolling semanal de validación
  - Script/daemon que revisa N planes/semana
  - Para cada plan: abrir app → ejecutar steps → verificar con OCR
  - Si falla → marcar como `invalid`, re-planificar en siguiente uso
- [ ] **4.2** Métricas y logging
  - Tasa de hit del cache
  - Tasa de éxito de planes cacheados vs frescos
  - Tiempo promedio con cache vs sin cache

### Fase 5: Seguridad y permisos
- [ ] **5.1** Sistema de permisos por acción
  - Acciones de escritorio (abrir app, click) → permitidas
  - Acciones de sistema (instalar paquetes, curl | sh) → confirmar
  - Acciones destructivas (rm -rf, formatear) → doble confirmación
- [ ] **5.2** Sandbox de ejecución de comandos
  - Comandos de terminal → mostrar preview antes de ejecutar
  - Flag `--auto-approve` para modo desatendido

---

## 🔧 Decisiones Técnicas Pendientes

| Decisión | Opciones | Estado |
|----------|----------|--------|
| LLM para descomposición | Qwen 1.5B (actual) vs 7B+ vs API externa | Qwen 1.5B para pruebas, escalar después |
| Backend del Skill Cache | SQLite + embeddings vs ChromaDB | Evaluar ambos |
| Formato de embeddings | Sentence-transformers vs LLM embeddings | Por decidir |
| Validación rolling | Daemon systemd vs cron vs manual | Por decidir |
| Formato de steps semánticos | JSON schema vs dataclass | Por decidir |

---

## 📐 Ejemplo: Flujo Completo v1.0

```
Usuario: "Créame y compílame un hola mundo en Rust"

1. Skill Cache lookup:
   → No hay match exacto, pero hay skills parciales:
     - "abrir_terminal" (confianza: 0.95) ✓ cached
     - "crear_archivo" (confianza: 0.90) ✓ cached
     - "compilar_rust" (confianza: 0.40) ✗ no cached

2. Decomposer (LLM):
   → Sub-tareas:
     a) abrir_terminal       → USE CACHED SKILL
     b) crear main.rs        → USE CACHED SKILL (parametrizado)
     c) escribir código      → NEW (LLM genera contenido)
     d) compilar con rustc   → NEW (LLM genera comando)

3. Ejecución:
   a) abrir_terminal:
      Cached: {intent: "launch_app", app: "kitty"}
      → executor.launch_app("kitty") ✓

   b) crear main.rs:
      Cached: {intent: "type_text", text: "touch main.rs && $EDITOR main.rs"}
      Resolve: type in focused terminal
      → executor.type_text(...) ✓

   c) escribir código:
      New plan from L2:
      → [{type: "type", text: "fn main() { println!(\"Hola mundo\"); }"}]
      → executor.type_text(...) ✓
      → CACHE this skill as "escribir_hola_mundo_rust"

   d) compilar:
      New plan from L2:
      → [{type: "type", text: "rustc main.rs && ./main"}]
      → executor.type_text(...) ✓
      → CACHE this skill as "compilar_rust_single_file"

4. TTS: "Listo, tu hola mundo en Rust está compilado y ejecutado"

5. Cache update:
   → Composite skill "crear_y_compilar_hola_mundo_rust" saved
   → Next time: entire task from cache in <1s
```