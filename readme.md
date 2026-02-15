# CecilOs: Inteligencia Artificial Multimodal para la Autonomía Digital

## Proyecto dedicado a devolver la independencia tecnológica a quienes más lo necesitan.

CecilOs es un ecosistema cognitivo diseñado para cerrar la brecha digital en adultos mayores y personas con discapacidad visual. A través de una arquitectura de agentes autónomos, el sistema transforma cualquier interfaz gráfica de Android en una experiencia puramente conversacional, eliminando la necesidad de interacción táctil compleja.

## Contexto Científico y Problemática
La "Exclusión Digital" actual se debe a tres fallos principales en el diseño de software:
1.  **Invisibilidad Semántica:** La falta de metadatos de accesibilidad impide el uso de lectores de pantalla tradicionales.
2.  **Carga Cognitiva:** Interfaces saturadas y flujos de navegación inconsistentes generan ansiedad tecnológica.
3.  **Entorno Dinámico:** El software evoluciona más rápido que las capacidades de adaptación de los usuarios vulnerables.

## La Innovación: Navegación Basada en Percepción
CecilOs no consulta el código de las aplicaciones; **las observa y aprende**. Utiliza modelos de visión computacional para interpretar la pantalla como lo haría un humano, construyendo un mapa mental (Grafo de Tareas) que permite al usuario navegar mediante comandos de voz naturales.

---

## Arquitectura del Sistema (Microservicios)

El sistema opera mediante una red de microservicios locales que garantizan privacidad y respuesta inmediata:

### Capa de Inteligencia y Memoria
*   **Knowledge Graph (UTG):** Almacena la estructura de navegación de las apps. Ante una actualización de la app, el sistema re-mapea automáticamente los cambios para que el usuario no perciba la interrupción.
*   **Vectorial RAG:** Provee contexto histórico, permitiendo que el asistente recuerde preferencias y hábitos del usuario.

### Capa de Percepción Visual
*   **Zero-Label Vision (OmniParser):** Detecta iconos, botones y texto sin necesidad de etiquetas previas del desarrollador. Es la clave para la "Navegación Universal".

### Interfaz de Voz de Bajo Consumo
*   **Activación Jerárquica:** Un modelo ultra-ligero de detección de palabras clave (Wake Word) mantiene el sistema en reposo, activando los motores pesados de lenguaje (Whisper) solo bajo demanda para optimizar la batería.

### Capa de Acción Sistémica
*   **Integración Shizuku:** Ejecuta acciones de nivel de sistema con precisión milimétrica, permitiendo clics, scrolls y gestos complejos sin intervención manual.

---

## Privacidad y Ética
A diferencia de los asistentes comerciales, CecilOs procesa toda la información **on-device**. Ninguna captura de pantalla ni grabación de voz sale del dispositivo del usuario, cumpliendo con los más altos estándares de protección de datos en entornos de asistencia médica y social.

---

## Tecnologías Clave
*   **Modelos:** Whisper.cpp (STT), OmniParser (VLM), Local LLM.
*   **Core:** Kotlin / Android System Services.
*   **Permisos:** Shizuku (System-level API).
*   **Datos:** Grafos de conocimiento vectorizados.

## Autores y dedicatorias
Jorge Luis Herrera Cecilia ,

**A simple boy dedicated to his family**
# **for my mother ,the best of my life .**