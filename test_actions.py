#!/usr/bin/env python3
"""
CecilOs — Test de Acciones Individuales.

Prueba cada acción de Cecil-Hand una por una.
Espera confirmación del usuario entre cada test.

Uso: python test_actions.py [número_test]
  Sin argumento: ejecuta todos secuencialmente
  Con número: ejecuta solo ese test (ej: python test_actions.py 1)
"""

import os
import sys
import time

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

from cecil_hand.executor import InputExecutor

# Colors
G = "\033[92m"
R = "\033[91m"
Y = "\033[93m"
B = "\033[94m"
BOLD = "\033[1m"
END = "\033[0m"

executor = InputExecutor()

def ask(msg):
    """Ask user to confirm result."""
    try:
        r = input(f"  {Y}→ {msg} (s/n): {END}").strip().lower()
        return r in ("s", "si", "sí", "y", "yes", "")
    except (EOFError, KeyboardInterrupt):
        print()
        return False

def header(num, title, desc):
    print(f"\n{BOLD}{'─'*60}")
    print(f"  TEST {num}: {title}")
    print(f"{'─'*60}{END}")
    print(f"  {B}Descripción:{END} {desc}")
    print(f"  {Y}Ejecutando en 3 segundos...{END}")
    time.sleep(3)


# ═══════════════════════════════════════════════════════════
# TEST 1: launch_app — Abrir app con hyprctl (NATIVO)
# ═══════════════════════════════════════════════════════════
def test_1():
    header(1, "LAUNCH APP: kitty (hyprctl nativo)",
           "Abre Kitty directamente con hyprctl dispatch exec. Sin launcher.")
    result = executor.launch_app("kitty")
    print(f"  {'✓' if result else '✗'} executor.launch_app('kitty') → {result}")
    time.sleep(2)
    return ask("¿Se abrió una terminal Kitty?")


# ═══════════════════════════════════════════════════════════
# TEST 2: launch_app — Abrir nautilus (explorador)
# ═══════════════════════════════════════════════════════════
def test_2():
    header(2, "LAUNCH APP: nautilus (explorador)",
           "Abre Nautilus directamente con hyprctl.")
    result = executor.launch_app("nautilus")
    print(f"  {'✓' if result else '✗'} executor.launch_app('nautilus') → {result}")
    time.sleep(2)
    return ask("¿Se abrió el explorador de archivos?")


# ═══════════════════════════════════════════════════════════
# TEST 3: launch_app — Abrir firefox (navegador)
# ═══════════════════════════════════════════════════════════
def test_3():
    header(3, "LAUNCH APP: firefox (navegador)",
           "Abre Firefox directamente con hyprctl.")
    result = executor.launch_app("firefox")
    print(f"  {'✓' if result else '✗'} executor.launch_app('firefox') → {result}")
    time.sleep(3)
    return ask("¿Se abrió Firefox?")


# ═══════════════════════════════════════════════════════════
# TEST 4: close_window — Cerrar ventana activa (hyprctl)
# ═══════════════════════════════════════════════════════════
def test_4():
    header(4, "CLOSE WINDOW (hyprctl killactive)",
           "Cierra la ventana activa. ⚠ Asegúrate de tener una ventana que puedas cerrar.")
    ok_to_proceed = ask("¿Hay una ventana que pueda cerrar sin problema?")
    if not ok_to_proceed:
        print(f"  {Y}Saltado.{END}")
        return True
    result = executor.close_window()
    print(f"  {'✓' if result else '✗'} executor.close_window() → {result}")
    return ask("¿Se cerró la ventana activa?")


# ═══════════════════════════════════════════════════════════
# TEST 5: key alt+F4 — Cerrar ventana (por teclas)
# ═══════════════════════════════════════════════════════════
def test_5():
    header(5, "KEY: alt+F4 (cerrar por teclas)",
           "Enfoca la ventana Kitty abierta y la cierra con Alt+F4.")
    # Enfocar kitty primero
    focused = executor.focus_window("kitty")
    if not focused:
        print(f"  {Y}No hay Kitty abierta. Saltado.{END}")
        return True
    time.sleep(0.5)
    ok_to_proceed = ask("¿Kitty está enfocada? (Confirma para cerrarla con Alt+F4)")
    if not ok_to_proceed:
        print(f"  {Y}Saltado.{END}")
        return True
    result = executor.key("alt+F4")
    print(f"  {'✓' if result else '✗'} executor.key('alt+F4') → {result}")
    return ask("¿Se cerró la ventana Kitty?")


# ═══════════════════════════════════════════════════════════
# TEST 6: open_launcher — Abrir Rofi
# ═══════════════════════════════════════════════════════════
def test_6():
    header(6, "OPEN LAUNCHER (Rofi)",
           "Abre el launcher Rofi directamente.")
    result = executor.open_launcher()
    print(f"  {'✓' if result else '✗'} executor.open_launcher() → {result}")
    time.sleep(2)
    ok = ask("¿Se abrió el launcher Rofi?")
    executor.key("Escape")
    return ok


# ═══════════════════════════════════════════════════════════
# TEST 7: type_text — Escribir texto
# ═══════════════════════════════════════════════════════════
def test_7():
    header(7, "TYPE: texto en terminal",
           "Abre una terminal, luego escribe 'echo hola CecilOs'.")
    executor.launch_app("kitty")
    time.sleep(2)
    result = executor.type_text("echo hola CecilOs", target_class="kitty")
    print(f"  {'✓' if result else '✗'} executor.type_text('echo hola CecilOs', target_class='kitty') → {result}")
    return ask("¿Apareció 'echo hola CecilOs' escrito en la terminal?")


# ═══════════════════════════════════════════════════════════
# TEST 8: key Return — Enter
# ═══════════════════════════════════════════════════════════
def test_8():
    header(8, "KEY: Return (enter)",
           "Presiona Enter en la terminal del test anterior (debe ejecutar el echo).")
    result = executor.key("Return")
    print(f"  {'✓' if result else '✗'} executor.key('Return') → {result}")
    time.sleep(1)
    return ask("¿Se ejecutó el comando y apareció 'hola CecilOs'?")


# ═══════════════════════════════════════════════════════════
# TEST 9: tap — Click en coordenadas
# ═══════════════════════════════════════════════════════════
def test_9():
    header(9, "TAP: click en centro pantalla",
           "Click izquierdo en el centro de la pantalla (960, 540).")
    result = executor.tap(960, 540)
    print(f"  {'✓' if result else '✗'} executor.tap(960, 540) → {result}")
    return ask("¿Se hizo un click visible en el centro de la pantalla?")


# ═══════════════════════════════════════════════════════════
# TEST 10: key ctrl+c — Cancelar comando (flujo completo)
# ═══════════════════════════════════════════════════════════
def test_10():
    header(10, "KEY: ctrl+c (cancelar comando — flujo completo)",
           "1) Abre kitty  2) Escribe 'sudo pacman -Syu'  3) Enter  4) Ctrl+C para cancelar")

    # Paso 1: Cerrar cualquier Kitty previa y abrir una nueva
    print(f"  {B}Paso 1:{END} Cerrando Kitty previa (si existe) y abriendo nueva...")
    # Focus and close any existing kitty first
    if executor.focus_window("kitty"):
        time.sleep(0.3)
        executor.close_window()
        time.sleep(0.5)
    executor.launch_app("kitty")
    time.sleep(2)
    ok1 = ask("¿Se abrió Kitty? (Confirma para continuar)")
    if not ok1:
        print(f"  {R}Abortado.{END}")
        return False

    # Paso 2: Escribir comando
    print(f"\n  {B}Paso 2:{END} Escribiendo 'sudo pacman -Syu' en Kitty...")
    time.sleep(1)
    executor.type_text("sudo pacman -Syu", target_class="kitty")
    time.sleep(1)
    ok2 = ask("¿Apareció 'sudo pacman -Syu' en la terminal?")
    if not ok2:
        print(f"  {R}Abortado.{END}")
        return False

    # Paso 3: Ejecutar con Enter
    print(f"\n  {B}Paso 3:{END} Presionando Enter para ejecutar...")
    time.sleep(1)
    executor.focus_window("kitty")
    time.sleep(0.3)
    executor.key("Return")
    time.sleep(3)
    ok3 = ask("¿Se está ejecutando pacman? (puede pedir contraseña, no importa)")

    # Paso 4: Cancelar con Ctrl+C
    print(f"\n  {B}Paso 4:{END} Enviando Ctrl+C para cancelar...")
    time.sleep(1)
    executor.focus_window("kitty")
    time.sleep(0.3)
    result = executor.key("ctrl+c")
    print(f"  {'✓' if result else '✗'} executor.key('ctrl+c') → {result}")
    time.sleep(1)
    return ask("¿Se canceló el comando? (debe aparecer ^C o volver al prompt)")


# ═══════════════════════════════════════════════════════════
# TEST 11: wait — Esperar
# ═══════════════════════════════════════════════════════════
def test_11():
    header(11, "WAIT: 2 segundos",
           "Espera 2 segundos. Debe contar sin error.")
    t0 = time.time()
    result = executor.wait(2.0)
    elapsed = time.time() - t0
    print(f"  {'✓' if result else '✗'} executor.wait(2.0) → {result} (tardó {elapsed:.1f}s)")
    return ask(f"¿Esperó correctamente ~2 segundos?")


# ═══════════════════════════════════════════════════════════
# TEST 12: maximize_window — Maximizar
# ═══════════════════════════════════════════════════════════
def test_12():
    header(12, "MAXIMIZE WINDOW",
           "Abre Kitty, la enfoca, y la maximiza (fullscreen). Luego la restaura.")
    # Cerrar kitty previa si existe
    if executor.focus_window("kitty"):
        time.sleep(0.3)
        executor.close_window()
        time.sleep(0.5)
    # Abrir nueva kitty
    executor.launch_app("kitty")
    time.sleep(2)
    ok1 = ask("¿Se abrió Kitty? (Confirma para maximizarla)")
    if not ok1:
        return False
    # Enfocar kitty (con reintento)
    focused = False
    for i in range(5):
        if executor.focus_window("kitty"):
            focused = True
            break
        print(f"  {Y}Reintentando foco ({i+1}/5)...{END}")
        time.sleep(1)
    if not focused:
        print(f"  {R}No se pudo enfocar Kitty.{END}")
        return False
    time.sleep(0.5)
    result = executor.maximize_window()
    print(f"  {'✓' if result else '✗'} executor.maximize_window() → {result}")
    ok = ask("¿Se maximizó la ventana Kitty? (Confirma y luego se restaurará)")
    # Restaurar
    executor.focus_window("kitty")
    time.sleep(0.3)
    executor.maximize_window()
    return ok


# ═══════════════════════════════════════════════════════════
# TEST 13: switch_workspace — Cambiar escritorio
# ═══════════════════════════════════════════════════════════
def test_13():
    header(13, "SWITCH WORKSPACE: ir a escritorio 2",
           "Cambia al workspace 2, luego vuelve al 1.")
    result = executor.switch_workspace(2)
    print(f"  {'✓' if result else '✗'} executor.switch_workspace(2) → {result}")
    time.sleep(2)
    ok = ask("¿Cambió al escritorio 2?")
    executor.switch_workspace(1)
    return ok


# ═══════════════════════════════════════════════════════════
# TEST 14: open_path — Abrir ruta/carpeta
# ═══════════════════════════════════════════════════════════
def test_14():
    header(14, "OPEN PATH: ~/Desktop",
           "Abre la carpeta Desktop con el gestor de archivos por defecto.")
    result = executor.open_path("~/Desktop")
    print(f"  {'✓' if result else '✗'} executor.open_path('~/Desktop') → {result}")
    time.sleep(2)
    return ask("¿Se abrió la carpeta Desktop en el explorador?")


# ═══════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════
def main():
    tests = [
        test_1, test_2, test_3, test_4, test_5, test_6,
        test_7, test_8, test_9, test_10, test_11, test_12,
        test_13, test_14,
    ]

    names = [
        "launch_app kitty",  "launch_app nautilus", "launch_app firefox",
        "close_window",      "key alt+F4",          "open_launcher",
        "type_text",         "key Return",           "tap click",
        "key ctrl+c",        "wait",                 "maximize_window",
        "switch_workspace",  "open_path",
    ]

    print(f"\n{BOLD}╔══════════════════════════════════════════════════════════╗")
    print(f"║     CecilOs — Test de Acciones (Cecil-Hand)             ║")
    print(f"╚══════════════════════════════════════════════════════════╝{END}")
    print(f"  Backend: {executor.backend}")
    print(f"  Tests disponibles: {len(tests)}")
    print(f"  {Y}⚠ Mantén la vista en tu pantalla durante los tests.{END}")

    # Specific test?
    if len(sys.argv) > 1:
        try:
            num = int(sys.argv[1])
            if 1 <= num <= len(tests):
                ok = tests[num - 1]()
                status = f"{G}PASÓ{END}" if ok else f"{R}FALLÓ{END}"
                print(f"\n  Test {num} ({names[num-1]}): {status}")
                return
            else:
                print(f"  {R}Test {num} no existe. Rango: 1-{len(tests)}{END}")
                return
        except ValueError:
            print(f"  {R}Uso: python test_actions.py [1-{len(tests)}]{END}")
            return

    # Run all
    results = {}
    for i, test_fn in enumerate(tests, 1):
        try:
            ok = test_fn()
            results[i] = ok
        except KeyboardInterrupt:
            print(f"\n  {Y}Interrumpido por el usuario.{END}")
            break
        except Exception as e:
            print(f"  {R}Error: {e}{END}")
            results[i] = False

    # Summary
    print(f"\n{BOLD}{'═'*60}")
    print(f"  RESUMEN DE TESTS")
    print(f"{'═'*60}{END}")

    passed = 0
    for i, name in enumerate(names, 1):
        if i in results:
            status = f"{G}✓ PASÓ{END}" if results[i] else f"{R}✗ FALLÓ{END}"
            if results[i]:
                passed += 1
        else:
            status = f"{Y}— NO EJECUTADO{END}"
        print(f"  Test {i:2d}: {name:25s} {status}")

    total = len(results)
    print(f"\n  {BOLD}Resultado: {passed}/{total} tests pasaron.{END}")

    if passed == total:
        print(f"  {G}🎉 ¡Todas las acciones funcionan! Listo para el Intent Parser.{END}")
    else:
        failed = [names[i-1] for i in results if not results[i]]
        print(f"  {R}⚠ Fallaron: {', '.join(failed)}{END}")


if __name__ == "__main__":
    main()
