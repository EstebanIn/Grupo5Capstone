# 0003 — Asistente IA docente y tutor del alumno

- **Estado:** aceptada
- **Fecha:** 2026-09-21
- **Objetivos específicos:** 5 y 6 (Guía 1), con ajuste de alcance

## Contexto

La Guía 1 definió tres asistentes: generador de instrumentos de evaluación,
asistente de resúmenes de notas y asistencia, y copiloto de uso. El equipo
decidió priorizar dos asistentes orientados a la labor pedagógica:

- **Docente:** crear pruebas, revisar pruebas, crear rúbricas y crear material de estudio.
- **Alumno:** un tutor en línea.

El tutor del alumno es nuevo respecto de la Guía 1. Los asistentes se
adelantaron a la autenticación por institución porque no dependen de ella: el
aislamiento entre instituciones ya funciona (ADR 0002).

## Alternativas evaluadas

| Tema | Opciones | Decisión y criterio |
|---|---|---|
| Acceso a datos | (a) el modelo consulta la base con herramientas o SQL; (b) **la aplicación arma el contexto y el modelo solo lo recibe** | (b): el modelo no puede leer ni filtrar datos por su cuenta. Un mensaje malicioso no puede ampliar lo que ve. |
| Contexto del tutor | (a) incluir nombre, notas y asistencia del alumno para personalizar; (b) **solo nivel y asignatura** | (b): son menores de edad y el nivel gratuito de la API puede usar lo enviado (Ley 21.719). La personalización se hace por nivel, no por persona. |
| Historial del tutor | (a) tabla en la base; (b) **sesión de Django** | (b): no se acumulan conversaciones de menores; el historial expira con la sesión. |
| Salida estructurada | (a) texto libre; (b) **JSON validado para pruebas y rúbricas** | (b): permite editar pregunta por pregunta y medir la corrección. |
| Nombre del modelo | (a) versión fija (`gemini-2.5-flash`); (b) **alias `gemini-flash-latest` con respaldo `gemini-flash-lite-latest`** | (b): al integrarlo, `gemini-2.5-flash` ya no estaba disponible para cuentas nuevas y `gemini-3.6-flash` estaba saturado (503). El alias sigue al modelo vigente y el respaldo cubre las saturaciones. |

## Decisión

- `colegio/ia/proveedor.py`: único punto que importa el SDK de Gemini
  (`google-genai`). Reintenta ante 429/500/503 y, si el modelo sigue saturado,
  pasa a los modelos de respaldo. Con `IA_PROVEEDOR=simulado` (sin key, y en las
  pruebas) responde con ejemplos fijos sin llamar a la API.
- `colegio/ia/dominio.py`: interfaz de dominio. Decide qué ve la IA: curso,
  nivel y asignatura. Nunca nombres, RUT, notas ni asistencia de alumnos.
- `colegio/ia/asistentes.py`: prompts, validación de las respuestas y cálculo
  del porcentaje corregido.
- `InstrumentoIA` guarda `contenido_ia` (borrador original) y `contenido`
  (versión del docente). Al aprobar se calcula el **porcentaje corregido**
  (1 − similitud de texto × 100): es el indicador de calidad comprometido en la
  Guía 1, y el panel muestra el promedio por docente.
- Todo lo generado es un borrador: el docente lo edita y lo aprueba. Una vez
  aprobado ya no es editable, y se puede imprimir con o sin pauta.
- Tutor: guía con preguntas y no entrega respuestas de tareas o pruebas.
  Rechaza temas no escolares, no pide datos personales y, ante señales de
  riesgo, deriva a un adulto de confianza, al profesor jefe, al 131 o al 133.
- El Markdown que genera la IA se escapa antes de convertirlo a HTML: el modelo
  no puede inyectar HTML ni scripts en la página.

## Verificación

- 25 pruebas nuevas (63 en total), todas con el proveedor simulado: flujo
  generar → editar → aprobar con medición del porcentaje; rechazo de campos
  vacíos; documento aprobado no editable; un docente no ve ni elimina
  documentos de otro; el docente solo puede usar sus propias cargas; un alumno
  no entra al asistente docente ni un docente al tutor; el alumno solo usa
  asignaturas de su curso; **el prompt del tutor no contiene nombre, apellido,
  RUT ni username del alumno**; errores de la IA se muestran sin crear nada;
  escapado del HTML.
- Prueba real contra Gemini (`gemini-flash-latest`): prueba de 3 preguntas
  (~10 s), rúbrica (~20 s) y tutor (~23 s). Ante "dame la respuesta de la
  guía", el tutor explicó con un ejemplo y devolvió la pregunta al estudiante.

## Ajuste: "Revisar prueba" pasa a ser "Corregir prueba"

La primera versión de "Revisar prueba" revisaba la **calidad** de una prueba,
como un colega. Lo que el equipo necesitaba era **corregir la prueba respondida
por un alumno** con la pauta de una prueba creada en el asistente. Por eso:

- La revisión de calidad sigue disponible como botón "Revisar calidad con IA"
  dentro de un borrador, con el texto ya cargado.
- **Corregir prueba** (solo sobre pruebas aprobadas, cuya pauta es definitiva):
  1. El docente sube fotos o PDF de la hoja respondida (hasta 5 archivos de 10 MB).
  2. La IA **solo transcribe** qué marcó el alumno en cada pregunta y distingue
     entre respondida, en blanco, doble marca, ilegible y no encontrada. Recibe
     el texto de la prueba **sin la pauta**, para que no "corrija" al leer, y
     nunca recibe el nombre del alumno.
  3. El docente confirma o ajusta cada respuesta; las dudosas aparecen
     destacadas. También se pueden ingresar a mano, sin IA.
  4. El puntaje y la nota los calcula el sistema de forma determinista (escala
     1.0 a 7.0 con 60% de exigencia; en blanco cuenta como incorrecta), no el
     modelo. Opcionalmente, la nota se registra en una evaluación del libro.
- Las imágenes no se guardan. Como la hoja puede tener el nombre del alumno y
  se envía a Gemini, la pantalla pide taparlo antes de subirla.
- `CorreccionPrueba` registra cuántas respuestas ajustó el docente respecto de
  la lectura de la IA: es la medida de calidad de la lectura.
- Prueba real con una hoja sintética de 6 preguntas (círculos a mano, una en
  blanco, una con doble marca, levemente girada): la lectura fue correcta en
  6 de 6.
- Segunda prueba real, con 6 casos sobre una prueba de 8 preguntas en 2 páginas
  (`Downloads/EduGestor/pruebas_ia/`). Leídos correctamente: todo correcto,
  preguntas en blanco, alternativas rellenas, PDF de 2 páginas, página faltante
  (las preguntas 6 a 8 salen como "no encontrada") y una respuesta borrada y
  reemplazada. **Limitación detectada:** con marcas en X de grafito, una doble
  marca (A y C) se leyó como A, con ambos modelos. Por eso el docente confirma
  cada lectura antes de calcular.
- El nivel gratuito tiene una cuota por modelo: al alcanzarla (429), el
  proveedor pasa al modelo de respaldo.

## Pendientes

- **Bases curriculares:** el OA lo escribe el docente. La indexación de las
  Bases Curriculares (una asignatura, dos niveles, según la Guía 1) permitiría
  elegir el OA desde una lista.
- **Medición de calidad:** falta fijar el criterio de aceptación del
  porcentaje corregido (por ejemplo, un promedio bajo 30%) y registrar la
  evaluación con docentes.
- **Límites de uso:** no hay un tope de solicitudes por usuario. Con muchos
  alumnos en el nivel gratuito se puede alcanzar el límite por minuto de la
  API.
- Asistente de resúmenes y copiloto de uso (Guía 1): siguen pendientes.
