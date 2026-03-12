"""
CecilOs — Intent Parser (Capa 1: Diccionario + Patrones).

Analiza un comando en lenguaje natural (español/inglés) y lo convierte
en una lista de acciones ejecutables por Cecil-Hand.

Intents soportados:
  OPEN_APP      — abrir una aplicación
  CLOSE_WINDOW  — cerrar ventana activa
  MAXIMIZE      — maximizar ventana
  MINIMIZE      — minimizar ventana
  TYPE_TEXT     — escribir texto
  OPEN_PATH     — abrir carpeta/archivo
  SWITCH_WS     — cambiar de workspace
  OPEN_LAUNCHER — abrir el launcher
  CANCEL        — cancelar (Ctrl+C)
  SCREENSHOT    — captura de pantalla
"""

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger("cecil.parser")


@dataclass
class Intent:
    """Parsed intent from a natural language command."""
    action: str
    entity: str = ""
    extra: dict = field(default_factory=dict)
    confidence: float = 1.0
    raw_command: str = ""


APP_ALIASES = {
    "navegador": "firefox", "browser": "firefox", "firefox": "firefox",
    "chrome": "google-chrome-stable", "chromium": "chromium", "brave": "brave",
    "terminal": "kitty", "consola": "kitty", "kitty": "kitty",
    "alacritty": "alacritty", "wezterm": "wezterm",
    "carpeta": "nautilus", "carpetas": "nautilus",
    "archivos": "nautilus", "archivo": "nautilus",
    "explorador": "nautilus", "nautilus": "nautilus",
    "files": "nautilus", "folder": "nautilus", "folders": "nautilus",
    "thunar": "thunar", "dolphin": "dolphin",
    "código": "code", "code": "code", "vscode": "code",
    "editor": "code", "visual studio": "code",
    "vim": "nvim", "neovim": "nvim",
    "spotify": "spotify", "música": "spotify", "musica": "spotify",
    "vlc": "vlc", "video": "vlc", "vídeo": "vlc",
    "discord": "discord", "telegram": "telegram-desktop",
    "whatsapp": "whatsapp-nativefier",
    "steam": "steam", "juegos": "steam", "lutris": "lutris",
    "configuración": "gnome-control-center", "settings": "gnome-control-center",
    "monitor": "gnome-system-monitor", "htop": "kitty -e htop",
    "calculadora": "gnome-calculator", "calculator": "gnome-calculator",
    "writer": "libreoffice --writer",
    "calc": "libreoffice --calc",
    "impress": "libreoffice --impress",
}

PATH_ALIASES = {
    "escritorio": "~/Desktop", "desktop": "~/Desktop",
    "descargas": "~/Downloads", "downloads": "~/Downloads",
    "documentos": "~/Documents", "documents": "~/Documents",
    "imágenes": "~/Pictures", "imagenes": "~/Pictures", "pictures": "~/Pictures",
    "home": "~", "casa": "~",
}

_OPEN_VERBS = r"(?:abr[eií]|abre(?:me)?|open|launch|lanz[aá]|inici[aá]|ejecut[aá]|pon(?:me)?|muestra(?:me)?|arranca)"
_CLOSE_VERBS = r"(?:cierr[aá]|cerr[aá]|close|kill|mata|quit|sal(?:ir)?|exit)"
_MAX_VERBS = r"(?:maximiz[aá]|maximize|fullscreen|pantalla completa|agranda)"
_MIN_VERBS = r"(?:minimiz[aá]|minimize|oculta|esconde|hide)"
_TYPE_VERBS = r"(?:escrib[eí]|escribeme|type|teclea|pon|redact[aá]|anot[aá])"
_WS_VERBS = r"(?:cambi[aá]|switch|ve? al?|mover?|ir|pasa(?:r|te)?)"
_CANCEL_VERBS = r"(?:cancel[aá]|stop|para|interrupt|abort)"
_SCREENSHOT_VERBS = r"(?:captur[aá]|screenshot|pantallazo|foto)"

# ── Layer 3: In-app interaction patterns ──────────────────
# These are commands that require interacting INSIDE an application.
# They get routed to the Vision+LLM+Keybindings pipeline (Layer 3).
_IN_APP_PATTERNS = [
    # Browser actions
    r"(?:nueva|new|abr[eí]r?)\s+(?:pestaña|tab|pesta[ñn]a)",
    r"(?:cerr[aá]r?|cierra)\s+(?:pestaña|tab|pesta[ñn]a)",
    r"(?:recarga|reload|refresca|actualiza)\s*(?:la)?\s*(?:página|pagina|page)?",
    r"(?:busca|search|encuentra|find)\s+",
    r"(?:ve? |navega |entra |go )(?:a |to )?",
    # Messaging actions
    r"(?:respond[eé]|reply|contest[aá]|envia|env[íi]a|send|manda)\s+",
    r"(?:respond[eé]|reply|contest[aá])\s+(?:el |al |a )?(?:mensaje|message)",
    # Editor actions
    r"(?:guard[aá]|save)\s*(?:el )?(?:archivo|file)?",
    r"(?:desha[cz]|undo|reha[cz]|redo)",
    r"(?:copi[aá]|copy|peg[aá]|paste|cort[aá]|cut)",
    r"(?:seleccion[aá]|select)\s+(?:todo|all)",
    r"(?:ir a|go to|ve a)\s+(?:l[íi]nea|line)\s+\d+",
    # File manager actions
    r"(?:cre[aá]|create|nueva|new)\s+(?:una? )?(?:carpeta|folder|directorio|directory)",
    r"(?:renamea|rename|renombr[aá])\s+",
    r"(?:elimin[aá]|delete|borr[aá]|remove|trash)\s+",
    # Media actions
    r"(?:paus[aá]|pause|play|reproduc[eí]|siguiente|next|anterior|previous|skip)",
    r"(?:sub[eí]|baj[aá]|sube|baja)\s*(?:el )?(?:volumen|volume)",
    # General in-app
    r"(?:click|clic|haz click|presiona|tap|toca)\s+(?:en |on )?",
    r"(?:scroll|desplaza|baja|sube)\s+(?:hacia |para )?",
]


def _normalize(text):
    text = text.lower().strip()
    text = re.sub(r"\s+", " ", text)
    text = text.strip("¿¡?!.,;:")
    return text


def _extract_app(text):
    words = text.split()
    for n in range(3, 0, -1):
        for i in range(len(words) - n + 1):
            chunk = " ".join(words[i:i+n])
            if chunk in APP_ALIASES:
                return APP_ALIASES[chunk]
    for w in words:
        if w in APP_ALIASES:
            return APP_ALIASES[w]
    return None


def _extract_path(text):
    for alias, path in PATH_ALIASES.items():
        if alias in text:
            return path
    match = re.search(r"(~?/[\w/.\-]+)", text)
    if match:
        return match.group(1)
    return None


def _extract_workspace(text):
    match = re.search(r"(?:workspace|escritorio|desktop|espacio)\s*(\d+)", text)
    if match:
        return int(match.group(1))
    match = re.search(r"al\s+(\d+)", text)
    if match:
        return int(match.group(1))
    return None


def _extract_typed_text(text):
    for pattern in [
        r"(?:escrib[eí]|escribeme|type|teclea|pon|redact[aá]|anot[aá])\s+",
    ]:
        cleaned = re.sub(pattern, "", text, count=1).strip()
        if cleaned and cleaned != text:
            cleaned = cleaned.strip("\"'")
            return cleaned
    return text


def parse(command):
    """
    Parse a natural language command into an Intent.
    Returns an Intent if recognized, None if not understood.
    """
    raw = command
    text = _normalize(command)

    if not text:
        return None

    if re.search(_CLOSE_VERBS, text):
        # "cierra la pestaña/tab" is IN_APP, not CLOSE_WINDOW
        if re.search(r"(?:pesta[ñn]a|tab)", text):
            return Intent("IN_APP", entity=text, confidence=0.85, raw_command=raw)
        return Intent("CLOSE_WINDOW", confidence=0.95, raw_command=raw)

    # ── Layer 3 detection: in-app interaction ─────────
    # Must check BEFORE open verbs, since "abre nueva pestaña" is IN_APP, not OPEN_APP
    for pattern in _IN_APP_PATTERNS:
        if re.search(pattern, text):
            # Exception: if the ONLY match is a direct app name, it's OPEN_APP not IN_APP
            # e.g. "abre firefox" should NOT be IN_APP, but "abre nueva pestaña" should
            # Also "crea una carpeta" should be IN_APP even though "carpeta" → nautilus
            app = _extract_app(text)
            open_match = re.match(r"(?:abre|abrir|open|pon)\s+(\S+)$", text)
            if app and open_match and open_match.group(1) in APP_ALIASES:
                break  # Let it fall through to OPEN_APP detection below
            return Intent("IN_APP", entity=text, confidence=0.85, raw_command=raw)

    if re.search(_CANCEL_VERBS, text):
        return Intent("CANCEL", confidence=0.9, raw_command=raw)

    if re.search(_SCREENSHOT_VERBS, text):
        return Intent("SCREENSHOT", confidence=0.9, raw_command=raw)

    if re.search(_MAX_VERBS, text):
        return Intent("MAXIMIZE", confidence=0.95, raw_command=raw)

    if re.search(_MIN_VERBS, text):
        return Intent("MINIMIZE", confidence=0.95, raw_command=raw)

    if re.search(_WS_VERBS, text) and _extract_workspace(text) is not None:
        ws = _extract_workspace(text)
        return Intent("SWITCH_WS", entity=str(ws), confidence=0.9, raw_command=raw)

    if re.search(_TYPE_VERBS, text):
        app = _extract_app(text)
        if app and re.match(r"pon(?:me)?\s", text):
            return Intent("OPEN_APP", entity=app, confidence=0.9, raw_command=raw)
        typed = _extract_typed_text(text)
        if typed and typed != text:
            return Intent("TYPE_TEXT", entity=typed, confidence=0.85, raw_command=raw)

    if re.search(_OPEN_VERBS, text):
        path = _extract_path(text)
        if path:
            return Intent("OPEN_PATH", entity=path, confidence=0.9, raw_command=raw)

        app = _extract_app(text)
        if app:
            return Intent("OPEN_APP", entity=app, confidence=0.95, raw_command=raw)

        if re.search(r"(?:launcher|menú|menu|aplicaciones|apps)", text):
            return Intent("OPEN_LAUNCHER", confidence=0.9, raw_command=raw)

        words = text.split()
        if len(words) >= 2:
            last = words[-1]
            if last not in ("el", "la", "los", "las", "un", "una", "de", "del", "al"):
                return Intent("OPEN_APP", entity=last, confidence=0.5, raw_command=raw)

    app = _extract_app(text)
    if app:
        return Intent("OPEN_APP", entity=app, confidence=0.6, raw_command=raw)

    path = _extract_path(text)
    if path:
        return Intent("OPEN_PATH", entity=path, confidence=0.5, raw_command=raw)

    return None
