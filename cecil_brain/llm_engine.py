"""
Cecil-Brain LLM Engine.

Wraps llama-cpp-python to provide local LLM inference for action planning.
Optimized for GTX 1650 (4GB VRAM) — uses Qwen2.5-3B-Instruct Q4_K_M (~2.1GB).
"""

import json
import logging
import os
import re
from typing import Dict, List, Optional

logger = logging.getLogger("cecil.brain")

# System prompt that instructs the LLM to generate action plans
SYSTEM_PROMPT = """Eres Cecil-Brain, el motor de razonamiento de CecilOs, un agente cognitivo para Linux (Hyprland/Wayland).

Tu trabajo es generar un plan de acciones JSON basado en:
1. El comando del usuario (lo que quiere hacer).
2. La estructura de la pantalla actual (elementos interactuables con coordenadas).
3. Los atajos de teclado disponibles de la app activa y del sistema.
4. Historial de tareas similares completadas exitosamente (si hay).

ACCIONES DISPONIBLES:
- {"type":"tap", "x":N, "y":N, "target":"descripción"} — Click izquierdo en coordenadas.
- {"type":"double_click", "x":N, "y":N, "target":"descripción"} — Doble click.
- {"type":"right_click", "x":N, "y":N, "target":"descripción"} — Click derecho (menú contextual).
- {"type":"type", "text":"texto"} — Escribe texto en el campo enfocado.
- {"type":"key", "key_combo":"combo"} — Presiona teclas. Combos: "ctrl+c", "ctrl+v", "ctrl+z", "ctrl+s", "ctrl+t", "ctrl+w", "Return", "Tab", "Escape", "BackSpace", "Delete", "ctrl+a", "super+q" (cerrar ventana).
- {"type":"scroll", "x":N, "y":N, "direction":"up|down", "clicks":N} — Scroll del ratón.
- {"type":"hover", "x":N, "y":N, "target":"descripción"} — Mover ratón sin click.
- {"type":"wait", "duration":N} — Esperar N segundos.
- {"type":"launch_app", "app":"nombre_ejecutable"} — Abrir aplicación directamente.
- {"type":"close_window"} — Cerrar la ventana activa.
- {"type":"focus_window", "window_class":"clase"} — Enfocar una ventana por su clase.

ESTRATEGIA DE INTERACCIÓN IN-APP:
Cuando el usuario quiere hacer algo DENTRO de una app (responder mensaje, nueva pestaña, etc.):
1. PRIMERO revisa si hay un atajo de teclado disponible → usa {"type":"key"} (más rápido y confiable).
2. SOLO si no hay atajo → usa {"type":"tap"} en las coordenadas del elemento UI.
3. Para escribir texto: primero enfoca el campo (tap o key), luego usa {"type":"type"}.
4. Para navegar a una URL: usa key ctrl+l (barra de direcciones), luego type la URL, luego key Return.

REGLAS:
1. Responde SOLO con JSON válido, sin texto adicional.
2. Usa coordenadas del centro de los elementos proporcionados en la pantalla.
3. Para abrir apps usa "launch_app" (NO simules teclado para abrir el launcher).
4. Para cerrar ventanas usa "close_window" (NO uses alt+F4).
5. PREFIERE atajos de teclado sobre clicks cuando estén disponibles.
6. Si no puedes completar la tarea, devuelve {"actions": [], "reasoning": "explicación"}.
7. Máximo 10 acciones por plan.
8. Incluye "reasoning" explicando tu plan brevemente.

FORMATO:
{"actions": [{"type": "...", ...}, ...], "reasoning": "..."}"""


class LLMEngine:
    """
    Local LLM inference engine using llama-cpp-python.

    Manages model loading, prompt construction, and JSON response parsing.
    """

    def __init__(
        self,
        model_path: str,
        n_gpu_layers: int = -1,
        n_ctx: int = 4096,
        n_threads: int = 4,
        temperature: float = 0.1,
        max_tokens: int = 1024,
    ):
        """
        Initialize the LLM engine.

        Args:
            model_path: Path to the GGUF model file.
            n_gpu_layers: Number of layers to offload to GPU (-1 = all).
            n_ctx: Context window size in tokens.
            n_threads: Number of CPU threads.
            temperature: Sampling temperature (lower = more deterministic).
            max_tokens: Maximum tokens to generate.
        """
        self._model_path = model_path
        self._n_gpu_layers = n_gpu_layers
        self._n_ctx = n_ctx
        self._n_threads = n_threads
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._llm = None

        if not os.path.isfile(model_path):
            raise FileNotFoundError(
                f"Model not found: {model_path}\n"
                "Download it with:\n"
                "  huggingface-cli download Qwen/Qwen2.5-3B-Instruct-GGUF "
                "qwen2.5-3b-instruct-q4_k_m.gguf --local-dir ~/models/"
            )

    def load(self) -> None:
        """Load the LLM model into memory."""
        if self._llm is not None:
            return

        logger.info(f"Loading LLM model: {self._model_path}")
        logger.info(
            f"Config: gpu_layers={self._n_gpu_layers}, "
            f"ctx={self._n_ctx}, threads={self._n_threads}"
        )

        try:
            from llama_cpp import Llama

            self._llm = Llama(
                model_path=self._model_path,
                n_gpu_layers=self._n_gpu_layers,
                n_ctx=self._n_ctx,
                n_threads=self._n_threads,
                verbose=False,
            )
            logger.info("LLM model loaded successfully")
        except ImportError:
            raise ImportError(
                "llama-cpp-python not installed. Install with:\n"
                "  pip install llama-cpp-python "
                "--extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cu121"
            )
        except Exception as e:
            raise RuntimeError(f"Failed to load LLM model: {e}")

    def generate_action_plan(
        self,
        user_command: str,
        screen_layout: str,
        keybinding_context: str = "",
        active_app: str = "",
        cached_plans: Optional[List[Dict]] = None,
    ) -> Dict:
        """
        Generate an action plan from a user command and screen layout.

        Args:
            user_command: The user's voice command.
            screen_layout: JSON string of screen elements.
            keybinding_context: Formatted keybinding info for the active app.
            active_app: Name/class of the currently focused application.
            cached_plans: List of similar previously successful plans.

        Returns:
            Dictionary with "actions" (list) and "reasoning" (str).
        """
        if self._llm is None:
            self.load()

        # Build the user prompt
        user_prompt = f'Comando del usuario: "{user_command}"\n\n'

        if active_app:
            user_prompt += f"Aplicación activa: {active_app}\n\n"

        if keybinding_context:
            user_prompt += f"Atajos de teclado disponibles:\n{keybinding_context}\n\n"

        user_prompt += f"Pantalla actual:\n{screen_layout}\n\n"

        if cached_plans:
            user_prompt += "Tareas similares completadas exitosamente:\n"
            for i, plan in enumerate(cached_plans[:3]):  # Top 3
                user_prompt += f"{i+1}. Comando: \"{plan.get('command', '')}\"\n"
                user_prompt += f"   Plan: {json.dumps(plan.get('actions', []), ensure_ascii=False)}\n"
            user_prompt += "\n"

        user_prompt += "Genera el plan de acciones:"

        try:
            response = self._llm.create_chat_completion(
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=self._temperature,
                max_tokens=self._max_tokens,
                response_format={"type": "json_object"},
            )

            content = response["choices"][0]["message"]["content"]
            return self._parse_response(content)

        except Exception as e:
            logger.error(f"LLM generation error: {e}")
            return {
                "actions": [],
                "reasoning": f"Error generating plan: {str(e)}",
            }

    def _parse_response(self, content: str) -> Dict:
        """Parse the LLM response into a structured action plan."""
        try:
            # Try direct JSON parse
            result = json.loads(content)
            if "actions" in result:
                return result
        except json.JSONDecodeError:
            pass

        # Try to extract JSON from markdown code block
        try:
            json_match = re.search(r"```(?:json)?\s*(.*?)```", content, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group(1))
                if "actions" in result:
                    return result
        except (json.JSONDecodeError, AttributeError):
            pass

        # Try to find JSON object in the response
        try:
            start = content.index("{")
            end = content.rindex("}") + 1
            result = json.loads(content[start:end])
            if "actions" in result:
                return result
        except (ValueError, json.JSONDecodeError):
            pass

        logger.warning(f"Could not parse LLM response as JSON: {content[:200]}")
        return {
            "actions": [],
            "reasoning": f"Failed to parse response: {content[:200]}",
        }

    def unload(self) -> None:
        """Unload the model from memory."""
        if self._llm is not None:
            del self._llm
            self._llm = None
            logger.info("LLM model unloaded")

    @property
    def loaded(self) -> bool:
        """Check if the model is loaded."""
        return self._llm is not None
