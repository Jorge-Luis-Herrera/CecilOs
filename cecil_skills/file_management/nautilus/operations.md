# Operaciones sobre Nautilus (GNOME Files)

A continuación, se detalla una matriz exhaustiva de todas las operaciones y acciones posibles sobre un objeto o vista dentro de Nautilus, agrupadas por categoría de interacción.

## 1. Navegación y Vistas (Navegación Visual / "Mirar" e "Ir")
- **Abrir Carpeta:** Navegar al directorio raíz, home, descargas, documentos, disco externo, red (Doble Clic local).
- **Retroceder / Avanzar:** Volver al directorio anterior o avanzar (Botones "<", ">" en la barra superior o atajos de ratón / Alt + Flechas).
- **Subir de Nivel:** Ir a la carpeta padre del directorio actual (Alt + Flecha Arriba).
- **Cambiar Vistas:**
  - Cambiar a "Vista de Lista" (Grid -> List).
  - Cambiar a "Vista de Iconos" (List -> Grid).
- **Ajustar Zoom:** Aumentar (Ctrl + `+`) o reducir (Ctrl + `-`) el tamaño de las miniaturas para ver mejor.
- **Mostrar/Ocultar Archivos Ocultos:** Mostrar archivos `.dotfiles` (Ctrl + H).
- **Ruta Editable:** Alternar entre barra de botones y campo de texto para escribir la ruta absoluta (Ctrl + L).

## 2. Creación y Generación (Operaciones Proactivas)
- **Crear Nueva Carpeta:** Crear un directorio vacío y quedar listo para escribir su nombre (Ctrl + Shift + N / Clic derecho -> Nueva carpeta).
- **Crear Documento Vacío:** Si se configuran plantillas, crear un `.txt` u otros desde el menú contextual.
- **Abrir Terminal Aquí:** Botón derecho -> "Abrir en una terminal".

## 3. Selección y Foco (Aseguramiento de Contexto)
- **Seleccionar Un Ítem:** Un clic exacto sobre un icono o fila.
- **Selección Múltiple Adjunta:** Marcar varios ítems continuos haciendo clic, luego Shift + Clic en otro rango.
- **Selección Múltiple Aleatoria:** Usar Ctrl + Clic sobre activos diferentes.
- **Seleccionar Todo:** Escoger todos los archivos del directorio (Ctrl + A).
- **Invertir Selección:** (Requiere menús adicionales o comandos de terminal, aunque clásicamente soportado por gestores).
- **Seleccionar por Patrón:** Abrir un cuadro (si está disponible/visible en extensiones) para seleccionar tipos `.png`, `.txt`.

## 4. Manipulación del Ítem (Modificación / "Mover los cubos")
- **Renombrar:** Cambiar el nombre del archivo seleccionado, lo cual levanta un cuadro de texto in-line (F2).
- **Mover / Copiar con Foco (Portapapeles):**
  - Cortar (Ctrl + X)
  - Copiar (Ctrl + C)
  - Pegar (Ctrl + V)
- **Arrastrar y Soltar (Drag & Drop):** Clic sostenido (MouseDown), mover el ratón de forma humana (Bezier/Easing) hasta una barra lateral o carpeta superior, y soltar (MouseUp).
- **Duplicar:** Crear una copia inmediata (normalmente se asume Copiar+Pegar).
- **Mover a la Papelera:** Borrado suave (Supr / Delete).
- **Eliminar Permanentemente:** Borrar sin pasar por papelera requiriendo posible diálogo de confirmación (Shift + Supr).

## 5. Búsqueda y Filtrado
- **Buscar y Filtrar Visualmente:** Hacer clic en el icono de lupa (o Ctrl + F) para buscar en el árbol actual de carpetas.
- **Filtrar por Tipos:** Al buscar, utilizar los menús desplegables para acotar la búsqueda por "Fecha", "Tipo" o "Propietario".

## 6. Operaciones de Ventana / Ventanas Múltiples (GNOME Shell)
- **Nueva Pestaña:** Abrir una pestaña dentro de la misma vista de Nautilus (Ctrl + T).
- **Cerrar Pestaña:** (Ctrl + W).
- **Nueva Ventana:** Replicar Nautilus en otro proceso/ventana (Ctrl + N).
- **Fijar / Maximizar:** Acciones compartidas con Hyprland pero desde los bordes de la app.

## 7. Metadatos y Propiedades
- **Abrir Propiedades:** Sacar la ventana modal para cambiar premisos de lectura/escritura o ver peso (Alt + Enter / Clic Derecho -> Propiedades).
- **Modificar Permisos:** Navegar en el modal (Pestaña "Permisos") y cambiar de Sólo lectura a Lectura+Escritura.
- **Comprimir/Extraer:** Usar las integraciones del menú click derecho para hacer archivos `.zip` o extraer `.tar.gz`.

*Documentación enfocada para el enrutamiento visual. Con Hyprland y Wayland, el bot debe "ver" si están estas barras y aplicar los clics sobre ellas en base al análisis de L3 de llm_engine.*
