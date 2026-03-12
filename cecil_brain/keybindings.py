"""
CecilOs — Keybinding Loader.

Parsea los keybindings de Hyprland y los expone como contexto
para que el LLM sepa qué atajos de teclado tiene disponibles.

También incluye keybindings "universales" de apps comunes
(Firefox, VS Code, terminal, etc.) que el LLM puede usar
para interactuar dentro de las aplicaciones.
"""

import logging
import os
import re
from typing import Dict, List

logger = logging.getLogger("cecil.keybindings")

# ── Keybindings universales de apps comunes ───────────────
# Estos son atajos que funcionan en casi todas las apps de cada categoría.
# El LLM los usa para interactuar DENTRO de la app sin necesitar coordenadas.

APP_KEYBINDINGS: Dict[str, List[Dict[str, str]]] = {
    # ── Navegadores (Firefox, Chrome, Brave, Chromium) ────
    "firefox": [
        {"keys": "ctrl+t",       "action": "Nueva pestaña"},
        {"keys": "ctrl+w",       "action": "Cerrar pestaña actual"},
        {"keys": "ctrl+shift+t", "action": "Reabrir pestaña cerrada"},
        {"keys": "ctrl+tab",     "action": "Siguiente pestaña"},
        {"keys": "ctrl+shift+tab", "action": "Pestaña anterior"},
        {"keys": "ctrl+l",       "action": "Enfocar barra de direcciones"},
        {"keys": "ctrl+k",       "action": "Enfocar barra de búsqueda"},
        {"keys": "ctrl+f",       "action": "Buscar en la página"},
        {"keys": "ctrl+r",       "action": "Recargar página"},
        {"keys": "ctrl+shift+r", "action": "Recargar sin caché"},
        {"keys": "alt+left",     "action": "Página anterior"},
        {"keys": "alt+right",    "action": "Página siguiente"},
        {"keys": "ctrl+d",       "action": "Agregar marcador"},
        {"keys": "ctrl+h",       "action": "Historial"},
        {"keys": "ctrl+j",       "action": "Descargas"},
        {"keys": "ctrl+shift+p", "action": "Ventana privada"},
        {"keys": "ctrl+shift+b", "action": "Mostrar/ocultar marcadores"},
        {"keys": "f11",          "action": "Pantalla completa"},
        {"keys": "ctrl+plus",    "action": "Aumentar zoom"},
        {"keys": "ctrl+minus",   "action": "Reducir zoom"},
        {"keys": "ctrl+0",       "action": "Restablecer zoom"},
        {"keys": "Escape",       "action": "Detener carga / cerrar diálogo"},
        {"keys": "ctrl+1",       "action": "Ir a pestaña 1"},
        {"keys": "ctrl+2",       "action": "Ir a pestaña 2"},
        {"keys": "ctrl+3",       "action": "Ir a pestaña 3"},
        {"keys": "ctrl+9",       "action": "Ir a última pestaña"},
    ],
    "google-chrome-stable": [],  # same as firefox, filled below
    "chromium": [],
    "brave": [],

    # ── Editores de código (VS Code) ──────────────────────
    "code": [
        {"keys": "ctrl+n",       "action": "Nuevo archivo"},
        {"keys": "ctrl+o",       "action": "Abrir archivo"},
        {"keys": "ctrl+s",       "action": "Guardar"},
        {"keys": "ctrl+shift+s", "action": "Guardar como"},
        {"keys": "ctrl+w",       "action": "Cerrar editor actual"},
        {"keys": "ctrl+shift+n", "action": "Nueva ventana"},
        {"keys": "ctrl+shift+p", "action": "Paleta de comandos"},
        {"keys": "ctrl+p",       "action": "Búsqueda rápida de archivo"},
        {"keys": "ctrl+shift+f", "action": "Buscar en archivos"},
        {"keys": "ctrl+f",       "action": "Buscar en archivo actual"},
        {"keys": "ctrl+h",       "action": "Buscar y reemplazar"},
        {"keys": "ctrl+g",       "action": "Ir a línea"},
        {"keys": "ctrl+backtick", "action": "Abrir/cerrar terminal integrado"},
        {"keys": "ctrl+shift+backtick", "action": "Nuevo terminal"},
        {"keys": "ctrl+b",       "action": "Toggle barra lateral"},
        {"keys": "ctrl+shift+e", "action": "Explorador de archivos"},
        {"keys": "ctrl+shift+x", "action": "Extensiones"},
        {"keys": "ctrl+shift+g", "action": "Control de código fuente (git)"},
        {"keys": "ctrl+shift+d", "action": "Debug"},
        {"keys": "ctrl+tab",     "action": "Cambiar entre editores abiertos"},
        {"keys": "ctrl+z",       "action": "Deshacer"},
        {"keys": "ctrl+shift+z", "action": "Rehacer"},
        {"keys": "ctrl+c",       "action": "Copiar"},
        {"keys": "ctrl+v",       "action": "Pegar"},
        {"keys": "ctrl+x",       "action": "Cortar"},
        {"keys": "ctrl+a",       "action": "Seleccionar todo"},
        {"keys": "ctrl+d",       "action": "Seleccionar siguiente ocurrencia"},
        {"keys": "ctrl+shift+k", "action": "Eliminar línea"},
        {"keys": "alt+up",       "action": "Mover línea arriba"},
        {"keys": "alt+down",     "action": "Mover línea abajo"},
        {"keys": "ctrl+shift+l", "action": "Seleccionar todas las ocurrencias"},
        {"keys": "f5",           "action": "Iniciar depuración"},
        {"keys": "ctrl+f5",      "action": "Ejecutar sin depurar"},
    ],

    # ── Terminal (Kitty, Alacritty) ───────────────────────
    "kitty": [
        {"keys": "ctrl+shift+t", "action": "Nueva pestaña"},
        {"keys": "ctrl+shift+w", "action": "Cerrar pestaña"},
        {"keys": "ctrl+shift+right", "action": "Siguiente pestaña"},
        {"keys": "ctrl+shift+left", "action": "Pestaña anterior"},
        {"keys": "ctrl+shift+enter", "action": "Nueva ventana (split)"},
        {"keys": "ctrl+shift+c", "action": "Copiar"},
        {"keys": "ctrl+shift+v", "action": "Pegar"},
        {"keys": "ctrl+shift+plus", "action": "Aumentar tamaño de fuente"},
        {"keys": "ctrl+shift+minus", "action": "Reducir tamaño de fuente"},
        {"keys": "ctrl+shift+backspace", "action": "Restablecer tamaño de fuente"},
        {"keys": "ctrl+shift+f5", "action": "Recargar configuración"},
        {"keys": "ctrl+shift+u",  "action": "Entrada Unicode"},
        {"keys": "ctrl+shift+h", "action": "Scroll hacia arriba"},
        {"keys": "ctrl+shift+end", "action": "Scroll al final"},
    ],

    # ── Archivos (Nautilus) ───────────────────────────────
    "nautilus": [
        {"keys": "ctrl+n",       "action": "Nueva ventana"},
        {"keys": "ctrl+t",       "action": "Nueva pestaña"},
        {"keys": "ctrl+w",       "action": "Cerrar pestaña"},
        {"keys": "ctrl+l",       "action": "Editar ruta de ubicación"},
        {"keys": "ctrl+f",       "action": "Buscar archivos"},
        {"keys": "ctrl+h",       "action": "Mostrar archivos ocultos"},
        {"keys": "ctrl+shift+n", "action": "Crear carpeta nueva"},
        {"keys": "ctrl+a",       "action": "Seleccionar todo"},
        {"keys": "ctrl+c",       "action": "Copiar archivos"},
        {"keys": "ctrl+v",       "action": "Pegar archivos"},
        {"keys": "ctrl+x",       "action": "Cortar archivos"},
        {"keys": "Delete",       "action": "Mover a papelera"},
        {"keys": "ctrl+z",       "action": "Deshacer"},
        {"keys": "F2",           "action": "Renombrar"},
        {"keys": "Return",       "action": "Abrir seleccionado"},
        {"keys": "alt+left",     "action": "Atrás"},
        {"keys": "alt+up",       "action": "Carpeta padre"},
    ],

    # ── Mensajería (Telegram, Discord) ────────────────────
    "telegram-desktop": [
        {"keys": "ctrl+f",       "action": "Buscar en chats"},
        {"keys": "ctrl+k",       "action": "Buscar chats/contactos"},
        {"keys": "Escape",       "action": "Cerrar diálogo/cancelar"},
        {"keys": "ctrl+shift+m", "action": "Silenciar chat"},
        {"keys": "ctrl+w",       "action": "Cerrar ventana"},
        {"keys": "ctrl+q",       "action": "Salir"},
        {"keys": "alt+up",       "action": "Chat anterior"},
        {"keys": "alt+down",     "action": "Chat siguiente"},
        {"keys": "ctrl+shift+o", "action": "Archivar chat"},
        {"keys": "Return",       "action": "Enviar mensaje"},
        {"keys": "shift+Return", "action": "Nueva línea en mensaje"},
        {"keys": "ctrl+Return",  "action": "Enviar mensaje (alternativo)"},
    ],
    "discord": [
        {"keys": "ctrl+k",       "action": "Búsqueda rápida"},
        {"keys": "ctrl+f",       "action": "Buscar en canal"},
        {"keys": "ctrl+shift+m", "action": "Silenciar/desilenciar micrófono"},
        {"keys": "ctrl+shift+d", "action": "Silenciar/desilenciar audio"},
        {"keys": "alt+up",       "action": "Canal anterior"},
        {"keys": "alt+down",     "action": "Canal siguiente"},
        {"keys": "Escape",       "action": "Cerrar popup / deseleccionar"},
        {"keys": "Return",       "action": "Enviar mensaje"},
        {"keys": "shift+Return", "action": "Nueva línea en mensaje"},
    ],

    # ── Multimedia ────────────────────────────────────────
    "spotify": [
        {"keys": "space",        "action": "Play/pausa"},
        {"keys": "ctrl+right",   "action": "Siguiente canción"},
        {"keys": "ctrl+left",    "action": "Canción anterior"},
        {"keys": "ctrl+up",      "action": "Subir volumen"},
        {"keys": "ctrl+down",    "action": "Bajar volumen"},
        {"keys": "ctrl+shift+down", "action": "Silenciar"},
        {"keys": "ctrl+l",       "action": "Buscar"},
        {"keys": "ctrl+s",       "action": "Guardar en biblioteca"},
        {"keys": "ctrl+r",       "action": "Repetir"},
        {"keys": "ctrl+shift+r", "action": "Aleatorio (shuffle)"},
    ],
    "vlc": [
        {"keys": "space",        "action": "Play/pausa"},
        {"keys": "n",            "action": "Siguiente"},
        {"keys": "p",            "action": "Anterior"},
        {"keys": "f",            "action": "Pantalla completa"},
        {"keys": "ctrl+up",      "action": "Subir volumen"},
        {"keys": "ctrl+down",    "action": "Bajar volumen"},
        {"keys": "m",            "action": "Silenciar"},
        {"keys": "ctrl+l",       "action": "Abrir lista de reproducción"},
        {"keys": "ctrl+o",       "action": "Abrir archivo"},
    ],

    # ── Universales (funcionan en casi cualquier app) ─────
    "_universal": [
        {"keys": "ctrl+c",       "action": "Copiar"},
        {"keys": "ctrl+v",       "action": "Pegar"},
        {"keys": "ctrl+x",       "action": "Cortar"},
        {"keys": "ctrl+z",       "action": "Deshacer"},
        {"keys": "ctrl+shift+z", "action": "Rehacer"},
        {"keys": "ctrl+a",       "action": "Seleccionar todo"},
        {"keys": "ctrl+s",       "action": "Guardar"},
        {"keys": "ctrl+f",       "action": "Buscar"},
        {"keys": "ctrl+w",       "action": "Cerrar pestaña/ventana"},
        {"keys": "ctrl+q",       "action": "Salir de la aplicación"},
        {"keys": "Tab",          "action": "Siguiente campo"},
        {"keys": "shift+Tab",    "action": "Campo anterior"},
        {"keys": "Return",       "action": "Confirmar/Enviar"},
        {"keys": "Escape",       "action": "Cancelar/Cerrar diálogo"},
    ],
}

# Alias: browsers comparten los mismos shortcuts que Firefox
for _alias in ("google-chrome-stable", "chromium", "brave"):
    APP_KEYBINDINGS[_alias] = APP_KEYBINDINGS["firefox"]


def load_hyprland_keybindings() -> List[Dict[str, str]]:
    """
    Parse Hyprland keybindings from the config files.

    Returns a list of dicts: {"keys": "super+q", "action": "Kill active window"}
    """
    keybindings = []

    # Possible config paths
    config_paths = [
        os.path.expanduser("~/.config/hypr/conf/keybindings/default.conf"),
        os.path.expanduser("~/.config/hypr/conf/keybinding.conf"),
        os.path.expanduser("~/.config/hypr/conf/custom.conf"),
    ]

    for config_path in config_paths:
        if not os.path.isfile(config_path):
            continue
        try:
            with open(config_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    kb = _parse_hypr_bind_line(line)
                    if kb:
                        keybindings.append(kb)
        except Exception as e:
            logger.warning(f"Error reading keybindings from {config_path}: {e}")

    logger.info(f"Loaded {len(keybindings)} Hyprland keybindings")
    return keybindings


def _parse_hypr_bind_line(line: str) -> Dict[str, str] | None:
    """Parse a single Hyprland bind line into a keybinding dict."""
    # Match: bind[flags] = MODS, KEY, dispatcher, [params]  # comment
    match = re.match(
        r"bind[a-z]*\s*=\s*(.+)",
        line,
    )
    if not match:
        return None

    rest = match.group(1)

    # Extract comment as action description
    comment = ""
    if "#" in rest:
        parts = rest.rsplit("#", 1)
        rest = parts[0].strip()
        comment = parts[1].strip()

    # Split by comma
    fields = [f.strip() for f in rest.split(",")]
    if len(fields) < 3:
        return None

    mods_raw = fields[0]   # e.g. "$mainMod SHIFT"
    key_raw = fields[1]    # e.g. "Q"
    dispatcher = fields[2] # e.g. "killactive"

    # Convert modifiers
    mods = _convert_mods(mods_raw)
    key = key_raw.lower().strip()

    # Skip mouse bindings and non-standard keys
    if key.startswith("mouse") or key.startswith("code:"):
        return None

    # Build human-readable key combo
    if mods:
        key_combo = "+".join(mods + [key])
    else:
        key_combo = key

    # Build action description from comment or dispatcher
    action = comment if comment else f"{dispatcher} {','.join(fields[3:]) if len(fields) > 3 else ''}".strip()

    return {"keys": key_combo, "action": action}


def _convert_mods(mods_raw: str) -> List[str]:
    """Convert Hyprland modifier names to standard names."""
    mods = []
    raw = mods_raw.upper().replace("$MAINMOD", "SUPER")
    if "SUPER" in raw:
        mods.append("super")
    if "CTRL" in raw:
        mods.append("ctrl")
    if "ALT" in raw:
        mods.append("alt")
    if "SHIFT" in raw:
        mods.append("shift")
    return mods


def get_keybindings_for_app(app_class: str) -> List[Dict[str, str]]:
    """
    Get keybindings relevant to a specific app.

    Returns app-specific bindings + universal bindings.
    """
    app_lower = app_class.lower()

    # Find the best match
    bindings = []

    # Check exact match first
    if app_lower in APP_KEYBINDINGS:
        bindings = APP_KEYBINDINGS[app_lower]
    else:
        # Fuzzy match
        for key in APP_KEYBINDINGS:
            if key != "_universal" and key in app_lower:
                bindings = APP_KEYBINDINGS[key]
                break

    # Always include universal shortcuts
    universal = APP_KEYBINDINGS.get("_universal", [])

    # Combine: app-specific first, then universal (skip duplicates)
    seen_keys = {b["keys"] for b in bindings}
    combined = list(bindings)
    for u in universal:
        if u["keys"] not in seen_keys:
            combined.append(u)

    return combined


def keybindings_to_context(
    app_class: str,
    include_hyprland: bool = True,
) -> str:
    """
    Build a compact keybinding context string for the LLM.

    Args:
        app_class: The active application class (e.g. "firefox", "code").
        include_hyprland: Whether to include system-level Hyprland bindings.

    Returns:
        A formatted string the LLM can use to decide between key combos and clicks.
    """
    parts = []

    # App-specific keybindings
    app_bindings = get_keybindings_for_app(app_class)
    if app_bindings:
        parts.append(f"Atajos de {app_class}:")
        for b in app_bindings:
            parts.append(f"  {b['keys']:25s} → {b['action']}")

    # Hyprland system keybindings (condensed — only the most useful)
    if include_hyprland:
        hypr = load_hyprland_keybindings()
        if hypr:
            parts.append("\nAtajos del sistema (Hyprland):")
            for b in hypr[:30]:  # Limit to keep context manageable
                parts.append(f"  {b['keys']:25s} → {b['action']}")

    return "\n".join(parts)
