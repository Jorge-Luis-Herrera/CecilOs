#!/usr/bin/env python3
"""
CecilOs — Test Suite Interactivo.

Prueba cada componente del sistema paso a paso para verificar
que CecilOs puede controlar tu sistema operativo.

Ejecutar:
    python3 test_system.py          # Todas las pruebas
    python3 test_system.py capture  # Solo captura de pantalla
    python3 test_system.py vision   # Solo visión (AT-SPI2 + OCR)
    python3 test_system.py hand     # Solo control de input
    python3 test_system.py brain    # Solo motor LLM
    python3 test_system.py flow     # Flujo completo simulado
"""

import json
import logging
import os
import sys
import time
import subprocess
import shutil

# Setup path
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("cecil.test")


# ═══════════════════════════════════════════════════════════
#  Colores para output bonito
# ═══════════════════════════════════════════════════════════
class C:
    OK = "\033[92m"     # Verde
    WARN = "\033[93m"   # Amarillo
    FAIL = "\033[91m"   # Rojo
    INFO = "\033[94m"   # Azul
    BOLD = "\033[1m"
    END = "\033[0m"

def ok(msg):    print(f"  {C.OK}✓{C.END} {msg}")
def warn(msg):  print(f"  {C.WARN}⚠{C.END} {msg}")
def fail(msg):  print(f"  {C.FAIL}✗{C.END} {msg}")
def info(msg):  print(f"  {C.INFO}ℹ{C.END} {msg}")
def header(msg): print(f"\n{C.BOLD}{'═'*60}\n  {msg}\n{'═'*60}{C.END}")
def subheader(msg): print(f"\n  {C.BOLD}── {msg} ──{C.END}")


# ═══════════════════════════════════════════════════════════
#  0. VERIFICACIÓN DE DEPENDENCIAS
# ═══════════════════════════════════════════════════════════
def check_dependencies():
    header("0. VERIFICACIÓN DE DEPENDENCIAS DEL SISTEMA")

    deps = {
        "grim":      ("Captura de pantalla Wayland", "sudo pacman -S grim"),
        "ydotool":   ("Control de input Wayland",    "sudo pacman -S ydotool"),
        "tesseract": ("OCR fallback",                "sudo pacman -S tesseract tesseract-data-spa tesseract-data-eng"),
    }

    missing = []
    for cmd, (desc, install) in deps.items():
        path = shutil.which(cmd)
        if path:
            ok(f"{cmd}: {desc} → {path}")
        else:
            fail(f"{cmd}: {desc} → NO INSTALADO")
            info(f"  Instalar con: {install}")
            missing.append(cmd)

    # Check ydotoold daemon
    if shutil.which("ydotool"):
        result = subprocess.run(["pgrep", "-x", "ydotoold"], capture_output=True)
        if result.returncode == 0:
            ok("ydotoold daemon: corriendo")
        else:
            warn("ydotoold daemon: NO corriendo")
            info("  Iniciar con: sudo systemctl enable --now ydotoold")

    # Check Python packages
    subheader("Paquetes Python")
    py_deps = {
        "gi": ("PyGObject / AT-SPI2", "sudo pacman -S python-gobject"),
        "llama_cpp": ("llama-cpp-python (LLM)", "pip install llama-cpp-python"),
        "chromadb": ("ChromaDB (cache)", "pip install chromadb"),
    }
    for module, (desc, install) in py_deps.items():
        try:
            __import__(module)
            ok(f"{module}: {desc}")
        except ImportError:
            if module == "chromadb":
                warn(f"{module}: {desc} → no instalado (opcional, usa fallback JSON)")
            else:
                fail(f"{module}: {desc} → NO INSTALADO")
            info(f"  Instalar con: {install}")
            missing.append(module)

    # Wayland check
    subheader("Entorno de escritorio")
    wayland = os.environ.get("WAYLAND_DISPLAY", "")
    xdg = os.environ.get("XDG_SESSION_TYPE", "")
    if wayland or xdg == "wayland":
        ok(f"Wayland detectado (WAYLAND_DISPLAY={wayland})")
    else:
        warn("Wayland NO detectado — xdotool/scrot se usarán como fallback")

    if missing:
        print(f"\n  {C.WARN}Hay {len(missing)} dependencia(s) faltante(s).{C.END}")
        if "ydotool" in missing:
            print(f"  {C.FAIL}⚡ ydotool es CRÍTICO para Wayland.{C.END}")
            print(f"  {C.BOLD}   xdotool NO puede controlar clicks en Wayland/Hyprland.{C.END}")
    else:
        ok("Todas las dependencias están instaladas")

    return missing


# ═══════════════════════════════════════════════════════════
#  1. TEST DE CAPTURA DE PANTALLA
# ═══════════════════════════════════════════════════════════
def test_capture():
    header("1. TEST DE CAPTURA DE PANTALLA")

    from cecil_vision.capture import ScreenCapture

    cap = ScreenCapture()
    info(f"Backend detectado: {cap.backend}")

    if not cap.available:
        fail("No hay backend de captura disponible")
        return False

    # Capturar
    info("Capturando pantalla...")
    t0 = time.time()
    path = cap.capture("test_capture")
    elapsed = time.time() - t0

    if path and os.path.isfile(path):
        size_kb = os.path.getsize(path) / 1024
        ok(f"Captura exitosa: {path}")
        ok(f"Tamaño: {size_kb:.0f} KB, Tiempo: {elapsed:.2f}s")

        # Verificar que es una imagen válida
        try:
            result = subprocess.run(
                ["file", path], capture_output=True, text=True
            )
            if "PNG" in result.stdout or "image" in result.stdout.lower():
                ok(f"Formato válido: {result.stdout.strip()}")
            else:
                warn(f"Formato inesperado: {result.stdout.strip()}")
        except Exception:
            pass

        return path
    else:
        fail("Captura falló")
        return False


# ═══════════════════════════════════════════════════════════
#  2. TEST DE VISIÓN (AT-SPI2 + OCR)
# ═══════════════════════════════════════════════════════════
def test_vision(screenshot_path=None):
    header("2. TEST DE VISIÓN (LECTURA DE PANTALLA)")

    from cecil_vision.parser import ScreenParser

    parser = ScreenParser()
    info(f"AT-SPI2: {'disponible' if parser._has_atspi else 'NO disponible'}")
    info(f"Tesseract: {'disponible' if parser._has_tesseract else 'NO disponible'}")

    # Test AT-SPI2
    subheader("AT-SPI2 (Árbol de accesibilidad)")
    if parser._has_atspi:
        t0 = time.time()
        elements = parser.parse_with_atspi()
        elapsed = time.time() - t0

        if elements:
            ok(f"Encontrados {len(elements)} elementos en {elapsed:.2f}s")
            # Mostrar los primeros 10
            print()
            print(f"  {'Rol':<20} {'Nombre':<30} {'Pos':<12} {'Estado'}")
            print(f"  {'─'*20} {'─'*30} {'─'*12} {'─'*15}")
            for el in elements[:15]:
                name = (el.get('text') or el.get('name', ''))[:29]
                role = el.get('role', '')[:19]
                pos = f"({el.get('x',0)},{el.get('y',0)})"
                state = el.get('state', '')[:14]
                print(f"  {role:<20} {name:<30} {pos:<12} {state}")
            if len(elements) > 15:
                print(f"  ... y {len(elements) - 15} elementos más")
        else:
            warn("AT-SPI2 no encontró elementos (¿hay alguna ventana abierta?)")
    else:
        fail("AT-SPI2 no disponible (necesita python-gobject + at-spi2-core)")

    # Test Tesseract OCR
    subheader("Tesseract OCR (fallback)")
    if parser._has_tesseract and screenshot_path:
        t0 = time.time()
        ocr_elements = parser.parse_with_ocr(screenshot_path)
        elapsed = time.time() - t0

        if ocr_elements:
            ok(f"OCR encontró {len(ocr_elements)} textos en {elapsed:.2f}s")
            for el in ocr_elements[:10]:
                print(f"    '{el.get('text', '')}'  pos=({el.get('x',0)},{el.get('y',0)})  conf={el.get('state','')}")
        else:
            warn("OCR no encontró texto en la captura")
    elif not parser._has_tesseract:
        warn("Tesseract no instalado — instalar con: sudo pacman -S tesseract tesseract-data-spa tesseract-data-eng")
    elif not screenshot_path:
        warn("No hay captura de pantalla para OCR (ejecuta test_capture primero)")

    # Test combinado
    subheader("Parser combinado")
    all_elements = parser.parse(screenshot_path)
    if all_elements:
        ok(f"Parser combinado: {len(all_elements)} elementos totales")
        # Generar JSON para el LLM
        json_str = parser.elements_to_json(all_elements)
        ok(f"JSON para LLM: {len(json_str)} caracteres")
        return all_elements
    else:
        warn("No se encontraron elementos (sin AT-SPI2 ni OCR)")
        return []


# ═══════════════════════════════════════════════════════════
#  3. TEST DE CONTROL DE INPUT (Cecil-Hand)
# ═══════════════════════════════════════════════════════════
def test_hand():
    header("3. TEST DE CONTROL DE INPUT (Cecil-Hand)")

    from cecil_hand.executor import InputExecutor

    executor = InputExecutor()
    info(f"Backend detectado: {executor.backend}")

    if not executor.available:
        fail("No hay backend de input disponible")
        fail("En Wayland/Hyprland, xdotool NO puede mover el mouse ni hacer clicks")
        info("Instala ydotool: sudo pacman -S ydotool")
        info("Inicia el daemon: sudo systemctl enable --now ydotoold")
        return False

    if executor.backend == "xdotool" and (
        os.environ.get("WAYLAND_DISPLAY") or
        os.environ.get("XDG_SESSION_TYPE") == "wayland"
    ):
        warn("xdotool detectado pero estás en Wayland")
        warn("xdotool puede escribir texto pero NO puede:")
        warn("  - Mover el mouse")
        warn("  - Hacer clicks")
        warn("  - Hacer swipe")
        info("Para control completo instala: sudo pacman -S ydotool")
        info("Y luego: sudo systemctl enable --now ydotoold")
        print()

    print(f"\n  {C.BOLD}⚠  ADVERTENCIA: Los siguientes tests van a controlar")
    print(f"  tu mouse y teclado. Tienes 5 segundos para cancelar (Ctrl+C).{C.END}\n")

    try:
        for i in range(5, 0, -1):
            print(f"  Iniciando en {i}...", end="\r")
            time.sleep(1)
        print("  Iniciando tests...    ")
    except KeyboardInterrupt:
        print("\n  Cancelado por el usuario.")
        return False

    results = {}

    # Test 1: Tecla (la más segura)
    subheader("Test 3.1: Simulación de tecla (Super → abrir launcher)")
    info("Presionando Super para abrir el launcher...")
    success = executor.key("super")
    if success:
        ok("Tecla 'super' enviada")
        info("¿Se abrió el launcher/menú? (esperando 2s para cerrar)")
        time.sleep(2)
        executor.key("Escape")
        ok("Escape enviado para cerrar")
    else:
        fail("No se pudo enviar la tecla")
    results["key"] = success

    time.sleep(1)

    # Test 2: Tipo texto — abrir terminal y escribir
    subheader("Test 3.2: Escribir texto")
    info("Abriendo una ventana de terminal para escribir texto...")
    # En Hyprland, intentar abrir terminal
    term_cmds = ["kitty", "alacritty", "foot", "gnome-terminal", "konsole", "xterm"]
    term_opened = False
    for term in term_cmds:
        if shutil.which(term):
            info(f"Usando terminal: {term}")
            subprocess.Popen([term], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            term_opened = True
            time.sleep(2)  # Esperar a que abra
            break

    if term_opened:
        test_text = "echo CecilOs funciona!"
        info(f"Escribiendo: '{test_text}'")
        success = executor.type_text(test_text)
        if success:
            ok("Texto escrito correctamente")
            info("Verifica en la terminal que se escribió el texto")
        else:
            fail("No se pudo escribir texto")
        results["type"] = success
        time.sleep(2)
    else:
        warn("No se encontró emulador de terminal")
        results["type"] = False

    # Test 3: Click (solo si ydotool)
    subheader("Test 3.3: Click del mouse")
    if executor.backend == "ydotool":
        info("Moviendo mouse al centro de la pantalla y haciendo click...")
        # Obtener resolución
        try:
            res = subprocess.run(
                ["hyprctl", "monitors", "-j"],
                capture_output=True, text=True, timeout=5
            )
            if res.returncode == 0:
                monitors = json.loads(res.stdout)
                if monitors:
                    w = monitors[0].get("width", 1920)
                    h = monitors[0].get("height", 1080)
                else:
                    w, h = 1920, 1080
            else:
                w, h = 1920, 1080
        except Exception:
            w, h = 1920, 1080

        cx, cy = w // 2, h // 2
        info(f"Click en ({cx}, {cy}) — centro de la pantalla")
        success = executor.tap(cx, cy)
        if success:
            ok(f"Click en ({cx}, {cy}) ejecutado")
        else:
            fail("Click falló")
        results["tap"] = success
    else:
        warn("Click requiere ydotool en Wayland (xdotool no funciona para clicks)")
        results["tap"] = False

    # Resumen
    subheader("Resumen de control de input")
    for test, passed in results.items():
        if passed:
            ok(f"{test}: funciona")
        else:
            fail(f"{test}: falló")

    return all(results.values())


# ═══════════════════════════════════════════════════════════
#  4. TEST DEL EVENT BUS
# ═══════════════════════════════════════════════════════════
def test_event_bus():
    header("4. TEST DEL EVENT BUS")

    from cecil_core.events import (
        EventType, WakeUpEvent, UserCommandEvent,
        ActionStep, ActionPlanEvent, ExecutionResultEvent,
    )
    from cecil_core.event_bus import EventBus

    bus = EventBus()
    log = []

    # Suscribir handlers
    bus.subscribe(EventType.WAKE_UP, lambda e: log.append(("wake", e)))
    bus.subscribe(EventType.USER_COMMAND, lambda e: log.append(("cmd", e)))
    bus.subscribe(EventType.ACTION_PLAN, lambda e: log.append(("plan", e)))

    # Publicar eventos
    bus.publish(WakeUpEvent(source="test-ear", trigger_phrase="Cecil", similarity=0.95))
    bus.publish(UserCommandEvent(source="test-ear", text="abre Firefox", confidence=0.88))
    bus.publish(ActionPlanEvent(
        source="test-brain",
        steps=[
            ActionStep(action_type="key", key_combo="super"),
            ActionStep(action_type="wait", duration=1.0),
            ActionStep(action_type="type", text="firefox"),
            ActionStep(action_type="key", key_combo="Return"),
        ],
        reasoning="Abrir launcher, escribir firefox, presionar enter",
        user_command="abre Firefox",
    ))

    if len(log) == 3:
        ok(f"EventBus: 3/3 eventos recibidos correctamente")
        for tag, event in log:
            ok(f"  {tag}: {event.event_type.name} from {event.source}")
    else:
        fail(f"EventBus: solo {len(log)}/3 eventos recibidos")
        return False

    # Test multi-suscripción
    count = [0]
    bus.subscribe(EventType.WAKE_UP, lambda e: count.__setitem__(0, count[0] + 1))
    bus.publish(WakeUpEvent(source="test"))
    if count[0] == 1:
        ok("Multi-suscripción funciona")
    else:
        fail("Multi-suscripción falló")

    return True


# ═══════════════════════════════════════════════════════════
#  5. TEST DE FLUJO COMPLETO SIMULADO
# ═══════════════════════════════════════════════════════════
def test_full_flow():
    header("5. FLUJO COMPLETO SIMULADO (sin LLM)")
    info("Simula el flujo: Comando → Captura → Visión → Plan → Ejecución")
    info("Usa un plan de acciones predefinido (no requiere el modelo LLM)")
    print()

    from cecil_core.events import (
        EventType, UserCommandEvent, ScreenCaptureRequestEvent,
        ScreenLayoutEvent, ScreenElement, ActionStep, ActionPlanEvent,
        ExecutionResultEvent,
    )
    from cecil_core.event_bus import EventBus
    from cecil_vision.capture import ScreenCapture
    from cecil_vision.parser import ScreenParser
    from cecil_hand.executor import InputExecutor

    bus = EventBus()
    capture = ScreenCapture()
    parser = ScreenParser()
    executor = InputExecutor()

    flow_log = []

    # Paso 1: Simular comando de usuario
    subheader("Paso 1: Comando del usuario")
    command = "abre Firefox"
    info(f'Comando simulado: "{command}"')
    flow_log.append("command")

    # Paso 2: Capturar pantalla
    subheader("Paso 2: Captura de pantalla")
    screenshot = capture.capture("test_flow")
    if screenshot:
        ok(f"Captura: {screenshot}")
        flow_log.append("capture")
    else:
        fail("Captura falló — no se puede continuar")
        return False

    # Paso 3: Parsear pantalla
    subheader("Paso 3: Visión / Parseo de pantalla")
    elements = parser.parse(screenshot)
    ok(f"Elementos detectados: {len(elements)}")
    if elements:
        json_layout = parser.elements_to_json(elements)
        ok(f"JSON para LLM: {len(json_layout)} chars")
        flow_log.append("vision")
    else:
        warn("Sin elementos — el LLM no tendría contexto visual")
        flow_log.append("vision-empty")

    # Paso 4: Plan simulado (lo que generaría el LLM)
    subheader("Paso 4: Plan de acciones (simulado, sin LLM)")
    plan = ActionPlanEvent(
        source="test-brain",
        steps=[
            ActionStep(action_type="key", key_combo="super"),
            ActionStep(action_type="wait", duration=1.5),
            ActionStep(action_type="type", text="firefox"),
            ActionStep(action_type="wait", duration=0.5),
            ActionStep(action_type="key", key_combo="Return"),
        ],
        reasoning="Abrir launcher con Super, escribir 'firefox', presionar Enter",
        user_command=command,
    )
    ok(f"Plan generado: {len(plan.steps)} pasos")
    for i, step in enumerate(plan.steps):
        detail = step.key_combo or step.text or f"{step.duration}s"
        info(f"  {i+1}. {step.action_type}: {detail}")
    flow_log.append("plan")

    # Paso 5: ¿Ejecutar?
    subheader("Paso 5: Ejecución")
    print(f"\n  {C.BOLD}⚠  ¿Ejecutar el plan? Esto va a:{C.END}")
    print(f"     1. Presionar Super (abrir launcher)")
    print(f"     2. Escribir 'firefox'")
    print(f"     3. Presionar Enter (lanzar Firefox)")
    print()

    try:
        response = input(f"  {C.INFO}¿Ejecutar? (s/n): {C.END}").strip().lower()
    except (EOFError, KeyboardInterrupt):
        response = "n"

    if response in ("s", "si", "sí", "y", "yes"):
        info("Ejecutando en 3 segundos...")
        time.sleep(3)

        success_count = 0
        for i, step in enumerate(plan.steps):
            detail = step.key_combo or step.text or f"{step.duration}s"
            info(f"Ejecutando paso {i+1}/{len(plan.steps)}: {step.action_type} → {detail}")

            step_ok = False
            if step.action_type == "key":
                step_ok = executor.key(step.key_combo)
            elif step.action_type == "type":
                step_ok = executor.type_text(step.text)
            elif step.action_type == "wait":
                step_ok = executor.wait(step.duration)
            elif step.action_type == "tap":
                step_ok = executor.tap(step.x, step.y)

            if step_ok:
                ok(f"Paso {i+1} completado")
                success_count += 1
            else:
                fail(f"Paso {i+1} falló")

            time.sleep(0.1)

        if success_count == len(plan.steps):
            ok(f"Ejecución completa: {success_count}/{len(plan.steps)} pasos exitosos")
            flow_log.append("execution-ok")
        else:
            warn(f"Ejecución parcial: {success_count}/{len(plan.steps)} pasos")
            flow_log.append("execution-partial")
    else:
        info("Ejecución omitida por el usuario")
        flow_log.append("execution-skipped")

    # Resumen
    subheader("Resumen del flujo")
    for step in flow_log:
        ok(step)

    return True


# ═══════════════════════════════════════════════════════════
#  6. TEST DEL LLM (Cecil-Brain)
# ═══════════════════════════════════════════════════════════
def test_brain():
    header("6. TEST DEL MOTOR LLM (Cecil-Brain)")

    from cecil_brain.llm_engine import LLMEngine

    # Check if model exists
    model_path = os.environ.get(
        "CECIL_LLM_MODEL",
        os.path.expanduser("~/qwen2.5-1.5b.gguf"),
    )

    if not os.path.isfile(model_path):
        # Fallback to default
        model_path = os.path.expanduser("~/models/qwen2.5-3b-instruct-q4_k_m.gguf")

    if not os.path.isfile(model_path):
        fail(f"Modelo LLM no encontrado en ninguna ruta.")
        info("Descárgalo con:")
        info("  huggingface-cli download Qwen/Qwen2.5-3B-Instruct-GGUF \\")
        info("    qwen2.5-3b-instruct-q4_k_m.gguf --local-dir ~/models/")
        return False

    try:
        import llama_cpp
        ok(f"llama-cpp-python instalado: {llama_cpp.__version__}")
    except ImportError:
        fail("llama-cpp-python no instalado")
        info("Instalar con:")
        info("  pip install llama-cpp-python \\")
        info("    --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cu121")
        return False

    info(f"Cargando modelo: {model_path}")
    info("Esto puede tardar 10-30 segundos la primera vez...")

    try:
        engine = LLMEngine(model_path=model_path)
        t0 = time.time()
        engine.load()
        load_time = time.time() - t0
        ok(f"Modelo cargado en {load_time:.1f}s")
    except Exception as e:
        fail(f"Error cargando modelo: {e}")
        return False

    # Test con un comando simple
    subheader("Test de generación de plan")
    fake_screen = json.dumps([
        {"name": "Firefox", "role": "push button", "x": 100, "y": 50, "state": "enabled"},
        {"name": "Terminal", "role": "push button", "x": 200, "y": 50, "state": "enabled"},
        {"name": "Files", "role": "push button", "x": 300, "y": 50, "state": "enabled"},
        {"name": "Search...", "role": "entry", "x": 500, "y": 30, "state": "editable"},
    ], ensure_ascii=False)

    test_commands = [
        "abre Firefox",
        "escribe hola mundo en la búsqueda",
    ]

    for cmd in test_commands:
        info(f'Comando: "{cmd}"')
        t0 = time.time()
        plan = engine.generate_action_plan(
            user_command=cmd,
            screen_layout=fake_screen,
        )
        gen_time = time.time() - t0

        if plan.get("actions"):
            ok(f"Plan generado en {gen_time:.1f}s: {len(plan['actions'])} acciones")
            ok(f"Razonamiento: {plan.get('reasoning', '')[:80]}")
            for action in plan["actions"]:
                info(f"  → {action}")
        else:
            warn(f"Plan vacío ({gen_time:.1f}s): {plan.get('reasoning', 'sin razón')}")
        print()

    engine.unload()
    ok("Modelo descargado de memoria")
    return True


# ═══════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════
def main():
    print(f"\n{C.BOLD}╔══════════════════════════════════════════════════════════╗")
    print(f"║           CecilOs — Test Suite Interactivo              ║")
    print(f"╚══════════════════════════════════════════════════════════╝{C.END}")

    # Parse args
    test_name = sys.argv[1] if len(sys.argv) > 1 else "all"

    if test_name == "deps":
        check_dependencies()
    elif test_name == "capture":
        check_dependencies()
        test_capture()
    elif test_name == "vision":
        check_dependencies()
        path = test_capture()
        test_vision(path if path else None)
    elif test_name == "hand":
        check_dependencies()
        test_hand()
    elif test_name == "brain":
        test_brain()
    elif test_name == "bus":
        test_event_bus()
    elif test_name == "flow":
        check_dependencies()
        test_full_flow()
    elif test_name == "all":
        missing = check_dependencies()
        test_event_bus()
        path = test_capture()
        test_vision(path if path else None)
        if not missing or "ydotool" not in missing:
            test_hand()
        else:
            header("3. TEST DE CONTROL DE INPUT (Cecil-Hand)")
            fail("Omitido — ydotool no instalado (crítico para Wayland)")
        test_brain()

        header("RESUMEN FINAL")
        print(f"""
  {C.BOLD}Para habilitar control COMPLETO del SO:{C.END}

  1. Instalar ydotool (control de mouse/teclado en Wayland):
     {C.INFO}sudo pacman -S ydotool{C.END}
     {C.INFO}sudo systemctl enable --now ydotoold{C.END}

  2. Instalar tesseract (OCR, opcional):
     {C.INFO}sudo pacman -S tesseract tesseract-data-spa tesseract-data-eng{C.END}

  3. Descargar modelo LLM (cerebro):
     {C.INFO}pip install huggingface-hub{C.END}
     {C.INFO}huggingface-cli download Qwen/Qwen2.5-3B-Instruct-GGUF \\
       qwen2.5-3b-instruct-q4_k_m.gguf --local-dir ~/models/{C.END}

  4. Instalar llama-cpp-python:
     {C.INFO}pip install llama-cpp-python \\
       --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cu121{C.END}

  5. Probar flujo completo:
     {C.INFO}python3 test_system.py flow{C.END}
""")
    else:
        print(f"\n  Tests disponibles: deps, capture, vision, hand, brain, bus, flow, all")
        print(f"  Uso: python3 test_system.py [test]\n")


if __name__ == "__main__":
    main()
