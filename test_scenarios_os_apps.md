# Matriz de Pruebas Extensiva: OS y Aplicaciones para CecilOS 🤖

Este documento recopila de manera estructurada absolutamente todas las acciones que un Agente Inteligente (L1 Decompositor, L2 OpenClaw, L3 Vision) debería poder automatizar. 

El objetivo es tener un mapa mental de "**qué magia se puede hacer**" e ir implementando o verificando cada bloque de habilidades (skills) en `cecil_simple.py` y `executor.py`.

---

## 🖥️ 1. Nivel Sistema Operativo (OS) y Gestor de Ventanas (Wayland/Hyprland)

### A. Gestión de Ventanas y Entorno
- [ ] **Abrir:** Lanzar apps mediante el sistema (rofi, wofi, dmenu o directo por clase de ventana).
- [ ] **Cerrar:** Cerrar de forma gracefully (Alt+F4 o botón X) vs Kill forzado (hyprctl dispatch killactive).
- [ ] **Foco:** Cambiar el foco a una ventana específica ("Trae firefox al frente").
- [ ] **Redimensionar / Mover:** Maximizar, minimizar, poner en modo mosaico (tiling) o ventana flotante, mover a una esquina de la pantalla.
- [ ] **Espacios de trabajo (Workspaces):** Mover una app al workspace 2, cambiar al workspace 3.
- [ ] **Notificaciones:** Leer la última notificación del sistema o limpiar notificaciones.

### B. Control del Sistema
- [ ] **Audio/Media:** Subir/bajar volumen general, mutear, play/pause medios globales.
- [ ] **Pantalla:** Subir/bajar brillo.
- [ ] **Conectividad:** Encender/apagar Wi-Fi, emparejar dispositivo Bluetooth (requiere interactuar con applet o CLI).
- [ ] **Energía:** Suspender, bloquear pantalla, reiniciar, apagar.
- [ ] **Portapapeles:** Leer texto actual del portapapeles, insertar un texto al portapapeles, limpiar historial (si usa cliphist / wl-clipboard).

---

## 📁 2. Nivel Sistema de Archivos y Explorador (Nautilus / CLI)

### A. Navegación (Lo que estábamos parcheando)
- [ ] **Abrir y Navegar:** Abrir Nautilus y moverse a una ruta exacta (e.g., `Ctrl+L` -> escribir `/home/usr/Desktop` -> `Enter`).
- [ ] **Navegación Relativa:** Habiendo una vista abierta, doble clic o seleccionar y Enter para entrar a una subcarpeta.
- [ ] **Búsqueda (Visual/Interna):** Usar el buscador nativo del gestor de archivos (`Ctrl+F`).

### B. Operaciones CRUD (Create, Read, Update, Delete)
- [ ] **Creación:** Crear nueva carpeta temporal, crear archivo de texto vacío.
- [ ] **Manipulación:** Seleccionar un archivo y renombrarlo (`F2`).
- [ ] **Movilidad:** Cortar/Copiar un archivo, navegar a otro sitio y pegar (`Ctrl+X/C` y `Ctrl+V`).
- [ ] **Arrastrar y Soltar (Drag & Drop):** Clic izquierdo sostenido desde archivo A hacia carpeta B.
- [ ] **Borrado:** Mover a la papelera (`Delete`) vs Borrado Permanente (`Shift+Delete`).
- [ ] **Propiedades:** Clic derecho -> Propiedades o `Alt+Enter` para ver tamaño de archivo.

---

## 🖐️ 3. Interacciones Elementales Universales (Ratón y Teclado)

Para que OpenClaw (o la Visión) opere sin API nativas, dominar estas acciones puramente humanas es vital:
- [ ] **Tipos de Clic:** Clic izquierdo, clic derecho (Menú contextual), doble clic, clic medio (scroll pulsado).
- [ ] **Scroll:** Scroll abajo, arriba, izquierda, derecha (útil para leer páginas web largas o terminales).
- [ ] **Hover:** Posicionar el ratón sobre un elemento sin hacer clic para revelar tooltips o menús desplegables.
- [ ] **Selección de texto general:** Hacer clic + arrastrar, o doble clic en palabra, o triple clic en párrafo.
- [ ] **Atajos Críticos:** `Ctrl+Z` (Deshacer), `Ctrl+Y` (Rehacer), `Ctrl+A` (Seleccionar Todo).

---

## 🌐 4. Casos Específicos por Aplicación (El verdadero Test L2/L3)

### A. Navegador Web (Firefox, Chrome, Brave)
- [ ] **Tabs:** Abrir nueva pestaña (`Ctrl+T`), cerrar pestaña activa (`Ctrl+W`), reabrir pestaña cerrada (`Ctrl+Shift+T`).
- [ ] **Navegación:** `Ctrl+L` ir a URL + escribir web + Enter.
- [ ] **Interacción de Página:** Hacer clic en la lupa, escribir término, hacer scroll para buscar información.
- [ ] **Formularios:** Hacer clic en "input", rellenar campos de login, marcar checkbox, desplegar selector y presionar "Submit".
- [ ] **Extracción:** "Copiar el texto del segundo párrafo del artículo en pantalla".
- [ ] **Modo Lector / Descargas:** Guardar la página web, descargar una imagen (Clic derecho -> Guardar imagen como).

### B. Editor de Código / Texto (VS Code, Gedit, Neovim)
- [ ] **Archivos:** `Ctrl+O` para abrir un proyecto, `Ctrl+S` para guardar.
- [ ] **Edición Multilínea:** Buscar y reemplazar en todo el archivo (`Ctrl+H`).
- [ ] **Visión/Contexto:** "Ve a la línea que dice \`task_type == 'navigate'\` y cámbiala a \`esc_l2\`". (Requiere mirar la pantalla, buscar la línea, hacer clic, seleccionar, sobreescribir).
- [ ] **Terminal de IDE:** Abrir panel inferior de terminal (e.g. `Ctrl+J`), ejecutar script allí.

### C. Terminal Emulator (Kitty / Bash / Fish)
- [ ] **Ejecución Asistida:** Ejecutar un comando (ej. `ls -la`), y si hay error (ej. comando no encontrado), leer la pantalla y lanzar un `sudo apt install xyz`.
- [ ] **Pipes e Historial:** Usar la flecha de arriba, modificar un comando anterior y re-ejecutarlo.
- [ ] **Salida y Abortos:** Presionar `Ctrl+C` para matar un proceso congelado.

### D. Aplicaciones de Mensajería / Multimedia (Discord, Spotify, VLC)
- [ ] **Discord/Telegram:** Hacer clic en el cajón de búsqueda, buscar un contacto "Pedro", ir a su chat, escribir mensaje, enviar.
- [ ] **VLC/Spotify:** Dar 'Play', adelantar 10 segundos, mirar cuánto tiempo falta (Visión OCR de números dinámicos).

---

## 🪄 5. Flujos Híbridos (La "Magia" Real 🔮)

Este es el objetivo final de Cecil. Aquí comprobamos si el sistema no solo sabe usar los botones, sino que comprende el flujo de trabajo entre aplicaciones.

1. **Investigación y Síntesis:** *"Abre Firefox, busca en Wikipedia 'Historia del Imperio Romano', copia el primer sumario, abre un archivo llamado 'roma.txt' en Gedit, pégalo, guárdalo y luego ciérralo."*
2. **Asistencia a Desarrolladores:** *"Abre el archivo log que falló en VSCode, pégale una mirada al error, luego abre el navegador, busca en StackOverflow ese error y dime si ves alguna solución."*
3. **Manejo de Archivos Visual:** *"Ve a la carpeta Descargas, toma todas las imágenes (.png y .jpg) y muévelas a una carpeta que se llame 'Fotos Vacaciones'."* 
4. **Reproducción desatendida:** *"Ábreme Spotify, busca la playlist 'Lo-Fi Chill', ponla en aleatorio y minimiza la ventana."*

---

> **Metodología de Implementación sugerida para CecilOS:**
> 1. Asegurarse de que el Nivel 3 (Visión OCR + Ydotool) pueda dar cualquier clic / teclear cualquier cosa.
> 2. L1 Decompositor analiza la petición de los **"Flujos Híbridos"** y la rompe en Tareas.
> 3. L2 OpenClaw asume el mando en aquellos de "Aplicación Web/Específica". 
> 4. Los pasos del nivel 1 y 2 se ejecutan desde el fallback si Openclaw falla en encontrar un Node web/DOM.
