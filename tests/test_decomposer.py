#!/usr/bin/env python3
"""
Test suite for Phase 3: Task Decomposer

Validates:
  1. Passthrough (simple single commands)
  2. Conjunction splitting (X y luego Y)
  3. Hello World decomposition (Rust, Python, C)
  4. Known atomic task types
  5. Dependency ordering
"""

import sys
import os

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

from cecil_brain.decomposer import decompose, TaskDecomposer, SubTask


def _show(result):
    print(f"  Método: {result.decomposition_method}  |  Confianza: {result.confidence:.0%}  |  Compuesto: {result.is_composite}")
    for st in result.subtasks:
        dep = f"  deps={st.depends_on}" if st.depends_on else ""
        print(f"  [{st.order}] {st.task_type:<20}  \"{st.command}\"  args={st.args}{dep}")


def test_passthrough():
    print("=" * 60)
    print("TEST 1: Passthrough — comando simple desconocido")
    print("=" * 60)
    r = decompose("haz algo misterioso")
    _show(r)
    assert not r.is_composite
    assert r.subtasks[0].task_type == "raw_command"
    print("✓ Passthrough correcto\n")


def test_open_app():
    print("=" * 60)
    print("TEST 2: Comando atómico — abrir app")
    print("=" * 60)
    cases = [
        ("abre firefox",      "open_app", "firefox"),
        ("abre el programa kitty", "open_app", "kitty"),
        ("lanza vscode",      "open_app", "vscode"),
        ("open gedit",        "open_app", "gedit"),
    ]
    for cmd, expected_type, expected_app in cases:
        r = decompose(cmd)
        st = r.subtasks[0]
        ok = st.task_type == expected_type and expected_app in st.args.get("app", "")
        print(f"  {'✓' if ok else '✗'}  \"{cmd}\"  →  {st.task_type}  app={st.args.get('app')}")
    print()


def test_terminal():
    print("=" * 60)
    print("TEST 3: Comando atómico — terminal")
    print("=" * 60)
    cases = ["abre una terminal", "abre la consola", "open a terminal", "abre terminal"]
    for cmd in cases:
        r = decompose(cmd)
        st = r.subtasks[0]
        ok = st.task_type == "open_terminal"
        print(f"  {'✓' if ok else '✗'}  \"{cmd}\"  →  {st.task_type}")
    print()


def test_run_command():
    print("=" * 60)
    print("TEST 4: Comando atómico — ejecutar/compilar")
    print("=" * 60)
    cases = [
        ("ejecuta rustc main.rs",   "run_command",  "rustc main.rs"),
        ("corre python3 script.py", "run_command",  "python3 script.py"),
        ("compila main.c",          "compile",       "main.c"),
    ]
    for cmd, expected_type, expected_cmd in cases:
        r = decompose(cmd)
        st = r.subtasks[0]
        ok = st.task_type == expected_type
        print(f"  {'✓' if ok else '✗'}  \"{cmd}\"  →  {st.task_type}  cmd={st.args.get('cmd')}")
    print()


def test_conjunction_split():
    print("=" * 60)
    print("TEST 5: Conjunciones — X y luego Y")
    print("=" * 60)
    cases = [
        "abre firefox y luego abre una terminal",
        "abre kitty y ejecuta ls",
        "abre vscode y después abre una terminal",
    ]
    for cmd in cases:
        r = decompose(cmd)
        print(f"  \"{cmd}\"")
        _show(r)
        assert r.is_composite, f"Expected composite for: {cmd}"
        assert len(r.subtasks) >= 2, f"Expected >=2 subtasks for: {cmd}"
        print(f"  ✓ {len(r.subtasks)} sub-tareas\n")


def test_hello_world_rust():
    print("=" * 60)
    print("TEST 6: Hello World — Rust")
    print("=" * 60)
    r = decompose("crea un hello world en rust")
    _show(r)
    assert r.is_composite
    assert r.subtasks[0].task_type == "open_terminal"
    assert r.subtasks[1].task_type == "create_file"
    assert r.subtasks[2].task_type == "run_command"
    assert r.subtasks[1].args["filename"] == "main.rs"
    assert "fn main" in r.subtasks[1].args["content"]
    assert "rustc" in r.subtasks[2].args["cmd"]
    assert r.subtasks[1].depends_on == [0]
    assert r.subtasks[2].depends_on == [1]
    print("✓ Rust hello world: 3 pasos, dependencias correctas\n")


def test_hello_world_python():
    print("=" * 60)
    print("TEST 7: Hello World — Python")
    print("=" * 60)
    r = decompose("haz un hola mundo en python")
    _show(r)
    assert r.subtasks[1].args["filename"] == "main.py"
    assert "print" in r.subtasks[1].args["content"]
    assert "python3" in r.subtasks[2].args["cmd"]
    print("✓ Python hello world correcto\n")


def test_hello_world_c():
    print("=" * 60)
    print("TEST 8: Hello World — C")
    print("=" * 60)
    r = decompose("escribe un hello world en c")
    _show(r)
    assert r.subtasks[1].args["filename"] == "main.c"
    assert "#include" in r.subtasks[1].args["content"]
    assert "gcc" in r.subtasks[2].args["cmd"]
    print("✓ C hello world correcto\n")


def test_type_text():
    print("=" * 60)
    print("TEST 9: Comando atómico — escribir texto")
    print("=" * 60)
    cases = [
        "escribe hola mundo",
        "teclea print hello",
        "escríbeme def main():",
    ]
    for cmd in cases:
        r = decompose(cmd)
        st = r.subtasks[0]
        ok = st.task_type == "type_text"
        print(f"  {'✓' if ok else '✗'}  \"{cmd}\"  →  {st.task_type}  text={st.args.get('text')}")
    print()


if __name__ == "__main__":
    print("\n🧩 CecilOs Phase 3 Test Suite")
    print("Task Decomposer — Complex Commands → Atomic Sub-Tasks\n")

    test_passthrough()
    test_open_app()
    test_terminal()
    test_run_command()
    test_conjunction_split()
    test_hello_world_rust()
    test_hello_world_python()
    test_hello_world_c()
    test_type_text()

    print("=" * 60)
    print("✓ Todos los tests de Fase 3 completados")
    print("=" * 60)
