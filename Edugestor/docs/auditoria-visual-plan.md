# Auditoría visual de EduGestor: plan de optimización de espacio y layout

**Fecha:** 2026-11-24
**Alcance:** paneles de administración, docente, alumno y apoderado, además del Asistente IA (portada, documentos, operaciones, biblioteca, editor de material y estado de operación).
**Restricción:** se mantienen la estética actual, el color de cada rol, la tipografía, los radios, las tarjetas blancas con borde de acento y los botones verdes. Solo se cambian distribución, densidad, consistencia y comportamiento responsive.
**Evidencia:** capturas en `qa-asistente/*.png` (1440, 1920 y 390 px), CSS en `colegio/static/css/` y plantillas en `colegio/templates/`.

---

## 0. Resumen ejecutivo

| # | Hallazgo | Impacto | Esfuerzo |
|---|---|---|---|
| 1 | El menú de admin (12 ítems de 62 px) supera los 768 px de alto; como es `fixed` y `100vh` sin scroll, en laptops pequeñas se cortan "Cerrar sesión" y los últimos ítems | Alto (funcional) | Bajo |
| 2 | `admin.css` no tiene menú responsive: en móvil, el sidebar de 260 px tapa el contenido | Alto | Bajo |
| 3 | En móvil, el menú desplegado ocupa unos 430 px antes del contenido | Alto | Medio |
| 4 | Pasos 1-2-3 y aviso "Modo simulado" se repiten en todas las páginas IA (unos 110 px), incluso donde no hay flujo | Medio | Bajo |
| 5 | Tarjetas de herramientas IA con el ícono en una fila propia: unos 60 px perdidos por tarjeta, y unos 240 px por tarjeta en móvil | Medio | Bajo |
| 6 | KPIs en móvil apilados en 3 tarjetas de unos 135 px (unos 440 px en total) | Medio | Bajo |
| 7 | Sin ancho máximo en 1920 px: líneas de texto y tablas demasiado anchas | Medio | Bajo |
| 8 | En el editor de material, la barra fija "Guardar/Aprobar" corta la hoja y deja unos 100 px en blanco antes de la nota final | Medio | Bajo |
| 9 | Encabezados de página inconsistentes (3 variantes distintas) | Medio | Medio |
| 10 | Unos 200 `style=""` en línea: KPIs del docente con `<div>` de ícono vacío de 36 px | Medio | Medio |

---

## 1. Estructura global (shell)

### 1.1 Sidebar: altura y desbordamiento
- **Problema:** `.sidebar { position: fixed; height: 100vh }` en admin, docente, alumno y apoderado, sin `overflow-y`. En admin, el logo, los 12 ítems × (44 px + 18 px de margen) y el padding suman unos 890 px, más que una pantalla de 768 px.
- **Acción:**
  - Añadir `overflow-y: auto; display: flex; flex-direction: column;` a `.sidebar`.
  - Reducir `.menu li { margin-bottom }` de 18 px a 4 px y `.menu a { padding }` de 12 px a 10px 12px. La hoja de estilos del asistente (`ia_institucional.css`) ya usa ese ritmo.
  - Reducir `.logo { margin-bottom }` de 40 px a 24 px.
  - Fijar "Cerrar sesión" al fondo del sidebar (`margin-top: auto`) en lugar de `margin-top: 50px` entre los ítems de navegación. Hoy aparece en medio del menú en docente e IA.
- **Ahorro:** unos 200 px verticales en admin.

### 1.2 Sidebar: ancho unificado
- Hoy conviven 250 px (docente, alumno) y 260 px (admin, apoderado). Unificar en **240 px** con una variable `--sidebar-w`, usada también por `.main { margin-left }`. Se ganan entre 10 y 20 px de contenido.

### 1.3 Navegación móvil (≤ 768 px)
- **Problema:** el sidebar pasa a `position: relative` y muestra todo el menú, el subnav IA y el selector de proveedor (unos 430 px) antes del contenido. `admin.css` no tiene ninguna regla para este caso.
- **Acción:** usar una barra superior compacta de 56 px con el logo y un botón ☰. El menú se abre como panel con `<details>` o un toggle JS mínimo. El bloque "Proveedor de IA" queda dentro del panel. Aplicarlo también a admin.
- **Ahorro:** unos 370 px en la primera pantalla móvil.

### 1.4 Ancho máximo del contenido
- En 1920 px, tablas, párrafos y tarjetas se estiran (ver `mejora-visual-asistente-despues-1920.png`).
- **Acción:** usar `.main > *` o un contenedor `.page { max-width: 1320px; margin-inline: auto; }` y párrafos con `max-width: 75ch`. La pantalla "Estado de la operación" ya usa unos 1260 px; conviene unificar todas en el mismo valor.

### 1.5 Consolidar CSS por rol
- `admin.css`, `docente.css`, `alumno.css` y `apoderado.css` repiten unas 300 líneas casi idénticas (sidebar, topbar, cards, tablas, media queries).
- **Acción:** crear `base.css` con la estructura común y variables, y dejar en cada archivo de rol solo `--rol-acento`, `--rol-acento-oscuro` y `--rol-acento-suave`. El color de cada rol se mantiene. Así se aplica una sola vez todo lo de las secciones 1.1 a 1.4.

---

## 2. Sistema de espaciado y densidad

### 2.1 Escala de espaciado
- Hoy se usan 8, 10, 12, 14, 15, 16, 18, 20, 24, 25, 30, 40 y 50 px sin criterio.
- **Acción:** usar los tokens `--s1: 4px; --s2: 8px; --s3: 12px; --s4: 16px; --s5: 24px; --s6: 32px` y reemplazar los valores sueltos.

### 2.2 Tarjetas KPI
- **Asistente IA:** las 3 tarjetas miden unos 135 px de alto, con la etiqueta en mayúsculas, el número de 32 px y la descripción en filas separadas, más 28 px de padding.
  - Escritorio: padding de 28 px a 20 px, con unos 24 px de ahorro.
  - Móvil: tira horizontal de 3 columnas compactas (número + etiqueta corta) con la descripción como `title` o tooltip. Se pasa de unos 440 px a unos 90 px.
- **Panel docente (`panel_docente.html` l. 49-65):** cada KPI tiene un `<div style="font-size:28px; margin-bottom:8px"></div>` **vacío** que suma unos 36 px por tarjeta. Hay que eliminarlo y mover los estilos en línea a la clase `.kpi` compartida con el Asistente.

### 2.3 Tarjetas de herramientas (portada del Asistente)
- El ícono de 44 px ocupa una fila propia, seguido del título, la descripción y el botón (unos 220 px).
- **Acción:** poner el ícono a la izquierda del título en la misma fila (grid `auto 1fr`). Se ahorran unos 55 px por tarjeta.
- **Móvil:** quitar el botón de ancho completo y hacer que toda la tarjeta sea el enlace, con una flecha → en el extremo derecho. Cada tarjeta baja de unos 240 px a unos 110 px y las 4 caben en una pantalla.
- **Breakpoint:** en 1440 px se muestran 2 columnas y en 1920 px, 4. Usar `grid-template-columns: repeat(auto-fill, minmax(280px, 1fr))` para tener 3 o 4 columnas desde unos 1280 px.

### 2.4 Tablas
- **"Tus documentos":** filas de unos 63 px con cebra **y** borde. Conviene quedarse con una sola señal (borde inferior) y bajar el padding vertical a 10 px; cada fila queda en unos 52 px (aprox. 18 % más filas por pantalla).
- La columna "Fecha" repite el mismo día en todas las filas. Se puede agrupar por día con una fila separadora o mostrar la fecha relativa ("hoy 03:39").
- **Encabezado de tabla:** la banda verde sólida de 38 px puede pasar a 32 px. El color se mantiene.
- **Responsive:** solo `postulaciones` tiene `overflow-x: auto`. Hay que envolver todas las `table` en `.tabla-scroll { overflow-x: auto }` o, en ≤ 600 px, convertir las filas en tarjetas (`display: grid` por fila) en documentos, matrículas, notas, asistencia y pagos.

### 2.5 Lista de operaciones
- Cada operación ocupa unos 79 px: título en una línea, metadatos debajo y estado al extremo derecho, con unos 900 px vacíos en medio.
- **Acción:** pasar a una tabla compacta de una línea con Tipo · Proveedor · Fecha · Duración · Estado (unos 44 px). Se ve el doble de operaciones sin hacer scroll y aprovecha el ancho.

---

## 3. Jerarquía y consistencia de encabezados

### 3.1 Un solo patrón de cabecera de página
Hoy hay 3 variantes:
1. Tarjeta blanca con H1 y subtítulo (portada, documentos, operaciones).
2. Texto suelto "ESPACIO DOCENTE / Colegio…", seguido de los pasos, el aviso y una tarjeta con H1 (biblioteca, estado de operación).
3. Enlace "← Asistente docente" encima de la tarjeta (estado de operación).

**Propuesta:** un único bloque `page-header`, una fila sin tarjeta y sobre el fondo, con:
- a la izquierda, una miga de pan pequeña (`Asistente IA › Biblioteca`), el H1 y el subtítulo;
- a la derecha, el contexto (colegio · proveedor) y la acción principal de la página.

Eliminar la tarjeta blanca del encabezado ahorra unos 50 px de padding y sombra, y deja la tarjeta para el contenido. Si se quiere conservar la tarjeta por estética, igualmente hay que unificarla en todas las páginas.

### 3.2 Pasos del flujo (1 Configurar · 2 Revisar · 3 Aprobar)
- Hoy aparecen en documentos, operaciones y biblioteca, donde no hay flujo, y **nunca marcan el paso actual**. En la pantalla de estado se ven en otro estilo ("1 · Configurar", sin círculos).
- **Acción:** mostrarlos solo en crear, revisar y aprobar, resaltar el paso activo (círculo relleno con el acento) y unificar el estilo. Se ahorran unos 50 px en las demás pantallas.

### 3.3 Aviso "Modo simulado"
- Es un banner amarillo de unos 42 px más 20 px de margen en cada página. El sidebar y la cabecera ya muestran la etiqueta "Simulado".
- **Acción:** mostrar el banner completo solo en la portada y en las pantallas que generan contenido. En el resto basta la etiqueta ámbar junto al proveedor de la cabecera.

### 3.4 Acciones secundarias
- "Corregir respuestas →" es un botón con contorno, mientras que "Volver al asistente →" es un enlace subrayado en la misma posición.
- **Acción:** unificar en un botón secundario con contorno para acciones y un enlace sin subrayado y con flecha para volver.

### 3.5 Enlaces azules por defecto
- En la biblioteca, "Ficha oficial del Ministerio" y "Ver fuente original" usan el azul `#00e` del navegador, fuera de la paleta.
- **Acción:** `a { color: var(--ia-acento); }`, con subrayado solo al pasar el cursor.

---

## 4. Pantallas específicas

### 4.1 Biblioteca curricular
- **Doble anidación:** una tarjeta "Fuentes aprobadas" contiene otra tarjeta con la fuente, con 25 + 25 px de padding y sombra doble. Hay que aplanarla en una sola tarjeta con la fuente como fila.
- **Metadatos de la fuente** en 7 líneas separadas (asignatura, enlace, licencia, estado, fecha, versión, SHA). Se pueden agrupar en una grilla de definiciones de 2 o 3 columnas (`dl`) y dejar el SHA-256 truncado con botón "copiar". El bloque pasa de unos 330 px a unos 180 px.
- **Formulario de búsqueda:** el select mide 700 px, el input 100 % y el botón queda debajo. Mejor una sola fila (`select 280px | input 1fr | botón`), que ahorra unos 90 px.
- **Resultados:** "Leer fragmento completo" y "Ver fuente original · Búsqueda textual local" ocupan 2 filas. Conviene una sola fila de acciones y mostrar "Búsqueda textual local" una vez en el encabezado de resultados. Son unos 35 px por resultado, unos 175 px en 5 resultados.

### 4.2 Editor de material
- La barra fija inferior ("Sin cambios pendientes · Guardar · Aprobar") flota en medio de la hoja y la corta visualmente (`editor-material-1440.png`). Debe ser `position: sticky; bottom: 0` **dentro** del contenedor del editor, con fondo y sombra superior, o ir al final del formulario.
- Hay unos 100 px vacíos entre la casilla de confirmación y la nota "Al aprobar se registra…". La nota debe quedar pegada a la barra de acciones.
- La barra de formato usa "N" y "C" (negrita y cursiva) sin un ícono reconocible. Faltan `aria-label` y `title`, y conviene usar **B** con peso visual o *I* en cursiva para mantener el ancho y ganar claridad.
- Las pestañas (Explicación / Ejercicios / Solucionario) y "Vista del estudiante" van bien. El subtítulo repetido "Explicación y ejemplos" dentro del panel duplica la pestaña activa; se puede quitar el título y dejar solo la descripción (unos 25 px).

### 4.3 Estado de la operación
- Los estados Pendiente → Completado se ven como texto gris plano y no muestran cuál falló. Hay que convertirlos en un stepper con estados (✓ completado, ● actual y ✕ error en rojo).
- El mensaje de error está en texto plano junto a los pasos. Mejor un bloque de alerta roja con el texto y las acciones dentro.
- "Tiempo transcurrido: 0 s" y la lista de pasos internos pueden ir en un `<details>` de "Detalle técnico".

### 4.4 Panel docente (inicio)
- Los KPIs tienen estilos en línea y el `<div>` vacío de la sección 2.2.
- "Mis Cursos" es una lista con `style` en línea. Usar la misma tabla o lista compacta de la sección 2.5 con acciones a la derecha.

### 4.5 Reportes de admin (`panel_admin_reportes.html`)
- Los filtros por enseñanza son botones de colores con estilos en línea y el activo solo se distingue por `font-weight`. Conviene convertirlos en un *segmented control* o chips con el mismo alto y un estado activo claro (fondo de acento y texto blanco).
- La lista de cursos y el detalle se muestran uno debajo del otro. En ≥ 1280 px se pueden poner en 2 columnas (lista | detalle) para no perder el contexto.

### 4.6 Formularios (curso, matrícula, docente, alumno, apoderado)
- `form_curso.html` tiene 27 `style=""` y `max-width: 600px` en línea, y cada formulario usa un ancho distinto.
- **Acción:** usar `.form-card { max-width: 880px }` con `.form-grid` de 2 columnas en ≥ 768 px (ya existe en `docente.css`, pero no se usa en todas partes). Los formularios largos (postulación, matrícula, registrar alumno) se agrupan en `fieldset` con un título de sección. Así se reduce el scroll vertical en torno a un 40 %.
- Los mensajes de error en línea pasan a la clase `.alert-error` compartida.

---

## 5. Accesibilidad visual (sin cambiar la estética)
- **Contraste:** revisar `#9ca3af` sobre blanco (texto secundario de los KPIs del docente), que da 2.5:1 y no cumple AA. Subir a `#6b7280` (4.8:1).
- **Foco visible:** hoy los enlaces del menú solo tienen `:hover`. Añadir `:focus-visible` con el mismo estilo que el estado activo.
- **Hover del menú admin:** `transform: translateX(4px)` provoca un salto visual; con el `inset` del borde basta.
- **Objetivos táctiles en móvil:** que sean ≥ 44 px. Los sub-ítems "Tus documentos" y "Operaciones" miden unos 36 px.
- **Tipografía:** hoy se mezclan Poppins, Inter, Segoe UI y Arial. Definir una sola `--font-ui` por defecto con la fuente que ya domina en cada vista, sin cambiar la que se ve hoy, para evitar saltos entre páginas.

---

## 6. Plan de implementación por fases

### Fase 1: estructura (1-2 días, mayor impacto) ✅ implementada el 2026-11-25
> `static/css/base.css` se carga después del CSS de cada rol en las 25 plantillas con sidebar. `sidebar_active_script.html` agrega el botón "Menú" y envuelve las tablas en `.tabla-scroll`. Las filas flex en línea ahora usan `flex-wrap`.
> **Verificado** con 51 vistas renderizadas: no hay scroll horizontal en 390 px, "Cerrar sesión" se ve en 1366×768 y el menú móvil cerrado mide 68 px (antes, 490-766 px). Los 244 tests de Django pasan.
> **Pendiente:** el punto 2 (reducir los CSS de rol a variables) se dejó como capa de sobrescritura para no arriesgar regresiones; la deduplicación completa queda para la fase 4.

1. Crear `static/css/base.css` con tokens (espaciado, `--sidebar-w`, `--font-ui`, `--page-max`) y la estructura común (sidebar, main, topbar, card, table, kpi, page-header).
2. Reducir los 4 CSS de rol a variables de color y sus particularidades.
3. Sidebar: `overflow-y: auto`, ritmo de 4 px, "Cerrar sesión" con `margin-top: auto`.
4. Navegación móvil colapsable en los 5 bases (admin, docente, alumno, apoderado, IA).
5. `--page-max: 1320px` en el contenedor principal.
6. Envolver tablas en `.tabla-scroll`.

### Fase 2: componentes (1-2 días)
7. Componente `.kpi` único, con la variante móvil en tira de 3 columnas, aplicado al Asistente IA y al panel docente (borrando el `<div>` vacío).
8. Tarjetas de herramientas con el ícono en línea y la tarjeta completa clicable en móvil.
9. `page-header` único y migración de todas las páginas IA y de panel.
10. Pasos del flujo solo en crear, revisar y aprobar, con el paso activo marcado. El banner de modo simulado solo en la portada y en las pantallas de generación.
11. Enlaces con color de acento y botones secundarios unificados.

### Fase 3: pantallas (2-3 días)
12. Biblioteca: aplanar tarjetas, `dl` en grilla, búsqueda en una fila y acciones de resultado en una fila.
13. Editor: barra sticky dentro del contenedor, nota pegada a las acciones, quitar el subtítulo duplicado y añadir `aria-label` en la barra de formato.
14. Estado de operación: stepper con estados y alerta de error.
15. Operaciones: tabla compacta de una línea.
16. Documentos: filas de 52 px, una sola señal de separación y fecha relativa.
17. Reportes de admin: filtros como chips y vista en 2 columnas en ≥ 1280 px.
18. Formularios: `.form-card` + `.form-grid` en 2 columnas + `fieldset`, eliminando los estilos en línea.

### Fase 4: limpieza y verificación (1 día)
19. Eliminar los unos 200 `style=""` en línea que quedan (prioridad: `form_curso`, `panel_docente`, `form_matricula`, `panel_admin_reportes`, `panel_admin_matriculas`, `carga_masiva_cursos`).
20. Contraste AA, `:focus-visible` y objetivos táctiles de 44 px.
21. **Regresión visual:** extender `qa-asistente/capturar_evidencias.cjs` para capturar cada pantalla en 390, 768, 1366×768, 1440 y 1920, y comprobar:
    - `document.documentElement.scrollWidth <= innerWidth` (sin scroll horizontal);
    - que el último ítem del sidebar sea visible a 1366×768;
    - comparación antes y después en `docs/evidencias-auditoria/`.
22. Correr la suite de tests de Django (las plantillas cambian de clases, no de contexto).

---

## 7. Métricas de éxito

| Pantalla | Métrica | Antes | Objetivo |
|---|---|---|---|
| Portada IA (390 px) | Alto total | unos 2480 px | ≤ 1300 px |
| Portada IA (390 px) | Primera herramienta visible sin scroll | No (y ≈ 1350) | Sí (y < 800) |
| Portada IA (1440 px) | Herramientas visibles sin scroll | 2 de 4 | 4 de 4 |
| Admin (1366×768) | "Cerrar sesión" visible | No | Sí |
| Documentos (1440 px) | Filas visibles sin scroll | unas 11 | unas 14 |
| Operaciones (1440 px) | Filas visibles sin scroll | unas 5-6 | unas 12 |
| Biblioteca (1440 px) | Alto hasta el 1er resultado | unos 1230 px | ≤ 850 px |
| Todo el sitio | `style=""` en plantillas | unos 200 | ≤ 20 |
| Todo el sitio | Scroll horizontal en 390 px | Sí (admin y tablas) | No |

---

## 8. Estado de implementación (2026-11-25)

| Fase | Estado | Qué se hizo |
|---|---|---|
| 1. Estructura | ✅ | `base.css` común, sidebar con scroll y "Cerrar sesión" al fondo, menú móvil plegable, ancho máximo de 1320 px, tablas con scroll horizontal |
| 2. Componentes | ✅ | `_pasos.html` con el paso actual marcado (solo en crear → revisar → aprobar). Aviso de modo simulado fuera de documentos, operaciones y biblioteca. Encabezados unificados (contexto, ← Asistente IA, tarjeta). KPIs compactos (tira de 3 columnas en móvil). Tarjetas de herramientas con el ícono en línea y filas clicables en móvil. Enlaces con el color del módulo |
| 3. Pantallas | ✅ | Biblioteca: fuente plana con datos en grilla, SHA truncado con botón "Copiar", búsqueda en una fila y acciones de resultado en una fila. Editor: título duplicado oculto (accesible) y sombra en la barra fija. Estado de operación: etapas con ✓ y error como alerta. Operaciones y documentos: tablas compactas sin cebra. Reportes: filtros como chips y lista y detalle en 2 columnas (≥ 1280 px). Formularios: tarjeta de 880 px con campos en grilla |
| 4. Limpieza | ◐ parcial | Estilos en línea en `templates/colegio` (sin IA): unos 200 → 81 (meta ≤ 20 no alcanzada). Los restantes son en su mayoría estados que alterna JavaScript (`display:none`), colores por métrica del dashboard y bloques multilínea de `form_matricula` y `carga_masiva_cursos` |
| 5. Accesibilidad | ✅ | Texto `#9ca3af` → `#6b7280`, `:focus-visible` en el menú, sin salto `translateX` y objetivos de 44 px en el menú móvil |

**Correcciones a la auditoría original.** Dos hallazgos de la sección 4.2 resultaron ser efectos de las capturas de página completa, no defectos reales: la barra "Guardar/Aprobar" es `sticky` y en la captura aparece donde estaba el viewport, y el hueco de unos 100 px es su posición natural. Los botones "N" y "C" siguen la convención de Word en español y ya tenían `aria-label`, así que se mantuvieron.

**Fuera de alcance o pendiente.** La deduplicación completa de los 4 CSS de rol (ahora solo exportan `--rol-acento*`), unificar la tipografía, la fecha relativa en documentos y el resto de estilos en línea.

### Métricas medidas (vistas renderizadas con datos de ejemplo)

| Métrica | Antes | Después |
|---|---|---|
| Portada IA (390 px): alto total | unos 2480 px | 1060 px |
| Portada IA (1440 px): herramientas visibles sin scroll | 2 de 4 | 4 de 4 |
| Menú móvil cerrado | 490-766 px | 68 px |
| Admin (1366×768): "Cerrar sesión" visible | No | Sí |
| Scroll horizontal en 390 px (51 vistas) | admin y alumno | ninguna |
| Operaciones: alto por fila | unos 79 px | unos 39 px |
