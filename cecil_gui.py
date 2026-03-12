#!/usr/bin/env python3
"""
CecilOs — Interfaz de Pruebas.

GUI sencilla para probar cada componente de CecilOs:
  • Captura de pantalla
  • Visión (AT-SPI2 / OCR)
  • Control de input (ydotool)
  • Flujo completo simulado
"""

import json
import os
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
from PIL import Image, ImageTk

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

from cecil_core.events import (
    EventType, WakeUpEvent, UserCommandEvent,
    ScreenCaptureRequestEvent, ScreenLayoutEvent, ScreenElement,
    ActionStep, ActionPlanEvent, ExecutionResultEvent,
)
from cecil_core.event_bus import EventBus
from cecil_vision.capture import ScreenCapture
from cecil_vision.parser import ScreenParser
from cecil_hand.executor import InputExecutor


class CecilGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("CecilOs — Panel de Control")
        self.root.geometry("900x700")
        self.root.configure(bg="#1e1e2e")

        # Services
        self.bus = EventBus()
        self.capture = ScreenCapture()
        self.parser = ScreenParser()
        self.executor = InputExecutor()

        # State
        self.last_screenshot = None
        self.last_elements = []
        self.photo_image = None  # prevent GC

        self._build_ui()
        self._log("CecilOs GUI iniciada")
        self._log(f"  Captura: {self.capture.backend}")
        self._log(f"  Input:   {self.executor.backend}")
        self._log(f"  AT-SPI2: {'sí' if self.parser._has_atspi else 'no'}")
        self._log(f"  OCR:     {'sí' if self.parser._has_tesseract else 'no'}")
        self._log("─" * 50)

    # ── UI Build ──────────────────────────────────────────

    def _build_ui(self):
        style = ttk.Style()
        style.theme_use("clam")

        # Colors
        bg = "#1e1e2e"
        fg = "#cdd6f4"
        accent = "#89b4fa"
        surface = "#313244"
        green = "#a6e3a1"
        red = "#f38ba8"
        yellow = "#f9e2af"

        style.configure("TFrame", background=bg)
        style.configure("TLabel", background=bg, foreground=fg, font=("Cantarell", 11))
        style.configure("Title.TLabel", background=bg, foreground=accent, font=("Cantarell", 16, "bold"))
        style.configure("Status.TLabel", background=surface, foreground=green, font=("Cantarell", 10))
        style.configure("Action.TButton", font=("Cantarell", 11, "bold"), padding=8)
        style.configure("TNotebook", background=bg)
        style.configure("TNotebook.Tab", font=("Cantarell", 10, "bold"), padding=[12, 6])

        # Main frame
        main = ttk.Frame(self.root)
        main.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Title
        ttk.Label(main, text="🤖 CecilOs — Panel de Control", style="Title.TLabel").pack(pady=(0, 10))

        # Notebook (tabs)
        self.notebook = ttk.Notebook(main)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        self._build_capture_tab()
        self._build_hand_tab()
        self._build_flow_tab()
        self._build_log_tab()

    def _build_capture_tab(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="📸 Visión")

        # Top controls
        controls = ttk.Frame(tab)
        controls.pack(fill=tk.X, pady=5)

        btn_capture = ttk.Button(controls, text="📸 Capturar Pantalla", style="Action.TButton",
                                 command=self._on_capture)
        btn_capture.pack(side=tk.LEFT, padx=5)

        btn_parse = ttk.Button(controls, text="🔍 Analizar Pantalla", style="Action.TButton",
                               command=self._on_parse)
        btn_parse.pack(side=tk.LEFT, padx=5)

        self.capture_status = ttk.Label(controls, text="Sin captura", style="Status.TLabel")
        self.capture_status.pack(side=tk.RIGHT, padx=10)

        # Split: image left, elements right
        split = ttk.PanedWindow(tab, orient=tk.HORIZONTAL)
        split.pack(fill=tk.BOTH, expand=True, pady=5)

        # Image preview
        img_frame = ttk.Frame(split)
        split.add(img_frame, weight=1)

        self.img_label = tk.Label(img_frame, bg="#181825", text="Captura aparecerá aquí",
                                  fg="#6c7086", font=("Cantarell", 12))
        self.img_label.pack(fill=tk.BOTH, expand=True)

        # Elements list
        elem_frame = ttk.Frame(split)
        split.add(elem_frame, weight=1)

        ttk.Label(elem_frame, text="Elementos detectados:").pack(anchor=tk.W)
        self.elements_tree = ttk.Treeview(elem_frame, columns=("role", "pos", "state"),
                                          show="tree headings", height=15)
        self.elements_tree.heading("#0", text="Nombre")
        self.elements_tree.heading("role", text="Rol")
        self.elements_tree.heading("pos", text="Posición")
        self.elements_tree.heading("state", text="Estado")
        self.elements_tree.column("#0", width=150)
        self.elements_tree.column("role", width=100)
        self.elements_tree.column("pos", width=80)
        self.elements_tree.column("state", width=80)

        scrollbar = ttk.Scrollbar(elem_frame, orient=tk.VERTICAL, command=self.elements_tree.yview)
        self.elements_tree.configure(yscrollcommand=scrollbar.set)
        self.elements_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    def _build_hand_tab(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="🖱️ Control")

        ttk.Label(tab, text="Control de Input (ydotool)", style="Title.TLabel").pack(pady=10)

        # Key press
        key_frame = ttk.LabelFrame(tab, text="⌨️ Enviar Tecla", padding=10)
        key_frame.pack(fill=tk.X, padx=20, pady=5)

        self.key_entry = ttk.Entry(key_frame, width=30, font=("Cantarell", 12))
        self.key_entry.insert(0, "super")
        self.key_entry.pack(side=tk.LEFT, padx=5)

        ttk.Button(key_frame, text="Enviar", command=self._on_key).pack(side=tk.LEFT, padx=5)

        ttk.Label(key_frame, text="Ej: super, Return, ctrl+c, alt+F4",
                  font=("Cantarell", 9)).pack(side=tk.LEFT, padx=10)

        # Type text
        type_frame = ttk.LabelFrame(tab, text="📝 Escribir Texto", padding=10)
        type_frame.pack(fill=tk.X, padx=20, pady=5)

        self.type_entry = ttk.Entry(type_frame, width=40, font=("Cantarell", 12))
        self.type_entry.insert(0, "Hola desde CecilOs!")
        self.type_entry.pack(side=tk.LEFT, padx=5)

        ttk.Button(type_frame, text="Escribir", command=self._on_type).pack(side=tk.LEFT, padx=5)

        # Click
        click_frame = ttk.LabelFrame(tab, text="🖱️ Click en Coordenadas", padding=10)
        click_frame.pack(fill=tk.X, padx=20, pady=5)

        ttk.Label(click_frame, text="X:").pack(side=tk.LEFT)
        self.click_x = ttk.Entry(click_frame, width=6, font=("Cantarell", 12))
        self.click_x.insert(0, "960")
        self.click_x.pack(side=tk.LEFT, padx=5)

        ttk.Label(click_frame, text="Y:").pack(side=tk.LEFT)
        self.click_y = ttk.Entry(click_frame, width=6, font=("Cantarell", 12))
        self.click_y.insert(0, "540")
        self.click_y.pack(side=tk.LEFT, padx=5)

        ttk.Button(click_frame, text="Click", command=self._on_click).pack(side=tk.LEFT, padx=5)

        # Delay warning
        ttk.Label(tab, text="⚠️ Las acciones se ejecutan con 2s de delay para que puedas cambiar de ventana",
                  font=("Cantarell", 10)).pack(pady=15)

    def _build_flow_tab(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="🚀 Flujo Completo")

        ttk.Label(tab, text="Simulación de Flujo Completo", style="Title.TLabel").pack(pady=10)

        ttk.Label(tab, text="Escribe un comando como si hablaras con Cecil:",
                  font=("Cantarell", 11)).pack(pady=5)

        cmd_frame = ttk.Frame(tab)
        cmd_frame.pack(fill=tk.X, padx=20, pady=5)

        self.cmd_entry = ttk.Entry(cmd_frame, width=50, font=("Cantarell", 13))
        self.cmd_entry.insert(0, "abre Firefox")
        self.cmd_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)

        ttk.Button(cmd_frame, text="🚀 Ejecutar", style="Action.TButton",
                   command=self._on_flow).pack(side=tk.LEFT, padx=5)

        # Predefined commands
        predef_frame = ttk.LabelFrame(tab, text="Comandos predefinidos", padding=10)
        predef_frame.pack(fill=tk.X, padx=20, pady=10)

        commands = [
            ("Abrir Firefox", "abre Firefox"),
            ("Abrir Terminal", "abre la terminal"),
            ("Abrir Archivos", "abre el explorador de archivos"),
            ("Capturar pantalla", "toma una captura de pantalla"),
        ]
        for label, cmd in commands:
            ttk.Button(predef_frame, text=label,
                       command=lambda c=cmd: self._set_and_run_flow(c)).pack(side=tk.LEFT, padx=5)

        # Plan display
        ttk.Label(tab, text="Plan de acciones:", font=("Cantarell", 11, "bold")).pack(anchor=tk.W, padx=20, pady=(10, 0))

        self.plan_text = scrolledtext.ScrolledText(tab, height=12, font=("Cascadia Code", 10),
                                                    bg="#181825", fg="#cdd6f4",
                                                    insertbackground="#cdd6f4")
        self.plan_text.pack(fill=tk.BOTH, expand=True, padx=20, pady=5)

    def _build_log_tab(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="📋 Log")

        self.log_text = scrolledtext.ScrolledText(tab, height=20, font=("Cascadia Code", 10),
                                                   bg="#181825", fg="#cdd6f4",
                                                   insertbackground="#cdd6f4")
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        btn_frame = ttk.Frame(tab)
        btn_frame.pack(fill=tk.X, pady=5)
        ttk.Button(btn_frame, text="Limpiar log", command=lambda: self.log_text.delete("1.0", tk.END)).pack(side=tk.RIGHT, padx=5)

    # ── Actions ───────────────────────────────────────────

    def _log(self, msg: str):
        ts = time.strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{ts}] {msg}\n")
        self.log_text.see(tk.END)

    def _on_capture(self):
        self._log("Capturando pantalla...")
        t0 = time.time()
        path = self.capture.capture("gui_capture")
        elapsed = time.time() - t0

        if path and os.path.isfile(path):
            self.last_screenshot = path
            size_kb = os.path.getsize(path) / 1024
            self._log(f"✓ Captura: {path} ({size_kb:.0f} KB, {elapsed:.2f}s)")
            self.capture_status.config(text=f"✓ {size_kb:.0f}KB {elapsed:.2f}s")
            self._show_preview(path)
        else:
            self._log("✗ Captura falló")
            self.capture_status.config(text="✗ Error")

    def _show_preview(self, path: str):
        try:
            img = Image.open(path)
            # Resize to fit label
            w, h = self.img_label.winfo_width(), self.img_label.winfo_height()
            if w < 100: w = 400
            if h < 100: h = 300
            img.thumbnail((w, h), Image.Resampling.LANCZOS)
            self.photo_image = ImageTk.PhotoImage(img)
            self.img_label.config(image=self.photo_image, text="")
        except Exception as e:
            self._log(f"Error mostrando preview: {e}")

    def _on_parse(self):
        self._log("Analizando pantalla...")

        # Capture first if needed
        if not self.last_screenshot:
            self._on_capture()

        elements = self.parser.parse(self.last_screenshot)
        self.last_elements = elements
        self._log(f"Encontrados: {len(elements)} elementos")

        # Clear tree
        for item in self.elements_tree.get_children():
            self.elements_tree.delete(item)

        if elements:
            for el in elements:
                name = (el.get("text") or el.get("name", ""))[:30]
                role = el.get("role", "")
                pos = f"({el.get('x',0)},{el.get('y',0)})"
                state = el.get("state", "")
                self.elements_tree.insert("", tk.END, text=name,
                                          values=(role, pos, state))
        else:
            self._log("⚠ Sin elementos — instala tesseract para OCR:")
            self._log("  sudo pacman -S tesseract tesseract-data-spa tesseract-data-eng")

    def _on_key(self):
        key = self.key_entry.get().strip()
        if not key:
            return
        self._log(f"Enviando tecla '{key}' en 2s...")
        self._delayed_action(lambda: self._do_key(key))

    def _do_key(self, key: str):
        ok = self.executor.key(key)
        self.root.after(0, lambda: self._log(f"{'✓' if ok else '✗'} Tecla: {key}"))

    def _on_type(self):
        text = self.type_entry.get()
        if not text:
            return
        self._log(f"Escribiendo texto en 2s...")
        self._delayed_action(lambda: self._do_type(text))

    def _do_type(self, text: str):
        ok = self.executor.type_text(text)
        self.root.after(0, lambda: self._log(f"{'✓' if ok else '✗'} Texto: '{text[:30]}'"))

    def _on_click(self):
        try:
            x = int(self.click_x.get())
            y = int(self.click_y.get())
        except ValueError:
            self._log("✗ Coordenadas inválidas")
            return
        self._log(f"Click en ({x}, {y}) en 2s...")
        self._delayed_action(lambda: self._do_click(x, y))

    def _do_click(self, x: int, y: int):
        ok = self.executor.tap(x, y)
        self.root.after(0, lambda: self._log(f"{'✓' if ok else '✗'} Click: ({x}, {y})"))

    def _delayed_action(self, func):
        """Run an action after 2s delay in background thread."""
        def run():
            time.sleep(2)
            func()
        threading.Thread(target=run, daemon=True).start()

    # ── Flow ──────────────────────────────────────────────

    def _set_and_run_flow(self, cmd: str):
        self.cmd_entry.delete(0, tk.END)
        self.cmd_entry.insert(0, cmd)
        self._on_flow()

    def _on_flow(self):
        command = self.cmd_entry.get().strip()
        if not command:
            return

        self.plan_text.delete("1.0", tk.END)
        self._log(f"🚀 Flujo: '{command}'")

        # Generate a hardcoded plan based on the command
        plan = self._generate_simple_plan(command)

        # Show plan
        self.plan_text.insert(tk.END, f"Comando: \"{command}\"\n\n")
        for i, step in enumerate(plan):
            detail = step.get("detail", "")
            self.plan_text.insert(tk.END, f"  {i+1}. {step['type']}: {detail}\n")

        self.plan_text.insert(tk.END, f"\n── Ejecutando en 3 segundos... ──\n")
        self._log(f"Plan: {len(plan)} pasos — ejecutando en 3s")

        threading.Thread(target=self._execute_flow, args=(plan,), daemon=True).start()

    def _generate_simple_plan(self, command: str) -> list:
        """Generate a simple action plan without LLM (pattern matching)."""
        cmd = command.lower()

        if "firefox" in cmd:
            app = "firefox"
        elif "terminal" in cmd:
            app = "kitty"
        elif "archivo" in cmd or "explorador" in cmd or "files" in cmd:
            app = "nautilus"
        elif "código" in cmd or "code" in cmd or "vscode" in cmd:
            app = "code"
        elif "captura" in cmd or "screenshot" in cmd:
            return [
                {"type": "key", "detail": "Print", "key": "Print"},
            ]
        elif "escribe" in cmd or "escribir" in cmd:
            # Extract what to write
            text = cmd.split("escribe", 1)[-1].strip().strip('"').strip("'")
            if not text:
                text = "Hola desde CecilOs"
            return [
                {"type": "wait", "detail": "0.5s", "duration": 0.5},
                {"type": "type", "detail": text, "text": text},
            ]
        else:
            app = command.split()[-1] if command.split() else "firefox"

        return [
            {"type": "key", "detail": "super", "key": "super"},
            {"type": "wait", "detail": "1.5s", "duration": 1.5},
            {"type": "type", "detail": app, "text": app},
            {"type": "wait", "detail": "0.8s", "duration": 0.8},
            {"type": "key", "detail": "Return", "key": "Return"},
        ]

    def _execute_flow(self, plan: list):
        time.sleep(3)

        for i, step in enumerate(plan):
            step_type = step["type"]
            self.root.after(0, lambda s=step, n=i: self.plan_text.insert(
                tk.END, f"\n▶ Ejecutando paso {n+1}: {s['type']}...\n"))

            ok = False
            if step_type == "key":
                ok = self.executor.key(step["key"])
            elif step_type == "type":
                ok = self.executor.type_text(step["text"])
            elif step_type == "wait":
                time.sleep(step["duration"])
                ok = True
            elif step_type == "tap":
                ok = self.executor.tap(step.get("x", 0), step.get("y", 0))

            status = "✓" if ok else "✗"
            self.root.after(0, lambda s=status, n=i: [
                self.plan_text.insert(tk.END, f"  {s} Paso {n+1} completado\n"),
                self.plan_text.see(tk.END),
            ])
            self.root.after(0, lambda s=status, st=step: self._log(
                f"  {s} {st['type']}: {st['detail']}"))

            time.sleep(0.1)

        self.root.after(0, lambda: [
            self.plan_text.insert(tk.END, "\n── Flujo completado ──\n"),
            self._log("🏁 Flujo completado"),
        ])


# ── Main ──────────────────────────────────────────────────

def main():
    # Check PIL
    try:
        from PIL import Image, ImageTk
    except ImportError:
        print("Instalando Pillow para preview de imágenes...")
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "Pillow"])
        from PIL import Image, ImageTk

    root = tk.Tk()
    root.option_add("*tearOff", False)

    app = CecilGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
