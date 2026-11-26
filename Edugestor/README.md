# EduGestor e InnovaGestor

Aplicación Django de gestión escolar. El alcance del piloto es **una institución por instalación**. Ejecutar la aplicación de esta carpeta `Edugestor/`. La copia bajo `Fase 2/Evidencias Proyecto/Evidencias del sistema/Aplicacion/Edugestor/` es una evidencia diferente y no se sincroniza automáticamente.

## Asistente docente y pruebas

La rama incorpora web, PostgreSQL/pgvector, Redis, Celery worker y beat. Las operaciones docentes largas crean un `TrabajoIA` recuperable desde **Asistente → Operaciones recientes**. Mantener worker y beat activos. Crear respaldo antes de migrar una instalación con datos.

La [guía de pruebas con sus claves](docs/pruebas-manuales-asistente.md) explica cómo verificar Gemini y Qwen desde Registro de IA sin compartir credenciales. La [preparación gratuita de Oracle y Cloudflare](deploy/README.md) requiere cuentas y VM propias; conservar la instalación local.

Pruebas, rúbricas y materiales consultan el corpus curricular por asignatura y nivel. En **Biblioteca curricular** cada docente ve qué cursos tienen fuentes listas y puede proponer fuentes oficiales de curriculumnacional.cl; un administrador las aprueba en su panel y se indexan automáticamente ([detalle](docs/biblioteca-curricular.md#gestión-desde-la-interfaz)). El tutor conserva su propio índice. Cada borrador muestra las fuentes realmente recuperadas; recuperar una referencia no acredita por sí solo la alineación con un OA. Un objetivo introducido libremente queda identificado como personalizado.

Cada material abre con una ficha visual de una página, tipo infografía: título, subtítulo, una idea central ("¿Qué es…?"), de 4 a 8 tarjetas de colores con un ícono, una acción y una frase, y un "Recuerda" final. La IA entrega solo textos y el nombre de un ícono de un catálogo cerrado; el servidor valida, recorta y dibuja la ficha con SVG propios. El tipo **Ficha visual** genera solo esa página y un desafío corto; guía, resumen y ejercicios se piden con límites de extensión para que el material sea liviano. El docente edita la ficha (textos, íconos, tarjetas) antes de aprobar, y puede quitarla.

Los materiales nuevos separan explicación (incluidos ejemplos resueltos), ejercicios y solucionario. El docente revisa esa separación antes de aprobar. Las versiones del estudiante se construyen en el servidor, excluyendo los campos de pauta antes de renderizar; la descarga PDF usa WeasyPrint y las mismas plantillas que la vista de impresión. Un material antiguo aprobado se conserva y requiere una copia editable revisada antes de habilitar su exportación estudiantil.

Las pruebas combinan selección múltiple (1 punto cada una) con hasta cinco preguntas de desarrollo. En cada pregunta de desarrollo el estudiante responde en tres recuadros rotulados `P<n> · <nombre>`: desarrollo o justificación, fórmula o concepto clave, y resultado o conclusión. En Matemática y Ciencias se pide el cálculo con cuadrícula; en las demás asignaturas, la justificación con líneas. La pauta docente incluye fórmula, desarrollo y resultado esperados, y un puntaje por criterio editable. Al corregir, la IA primero transcribe cada recuadro sin ver la pauta y luego sugiere un puntaje por criterio con la pauta, solo con texto. El docente confirma o ajusta cada puntaje; la nota usa el puntaje total con 60% de exigencia.

Los trabajos duran como máximo cinco minutos de ejecución; Qwen utiliza streaming interno con límite total de tres minutos, tiempos de conexión y lectura separados y diagnóstico seguro. Una respuesta parcial no crea un documento y no se repite automáticamente. Se conserva el proveedor y modelo elegidos. Los archivos de entrada se cifran temporalmente; los PDF privados caducan tras 24 horas y pueden volver a exportarse. Redis recibe solo UUID.

## Inicio en Windows

Instala Git y Docker Desktop. Con Docker encendido, desde PowerShell:

```powershell
# Desde la carpeta del repositorio clonado:
Set-Location .\Edugestor
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
docker compose up --build -d
docker compose ps
```

Abre <http://127.0.0.1:8000/>. Compose espera a PostgreSQL, ejecuta las migraciones y arranca Django. En inicios posteriores basta `docker compose up -d`. Consulta errores con `docker compose logs --tail 50 web`.

`docker compose down` detiene los servicios y conserva el volumen PostgreSQL `edugestor_edugestor_pgdata`. No uses `down -v` si quieres conservar los datos. No restaures volcados de `backups/` para iniciar una base existente. Antes de migrar, crea un respaldo nuevo con `pg_dump`.

Compose fija la imagen `pgvector/pgvector:0.8.7-pg17-trixie` y su digest, la misma validada localmente con PostgreSQL 17. Así, el inicio documentado no depende de un script ni de un override privado. Si ya tienes un volumen creado con otra distribución o versión de collation, conserva un respaldo y revisa su compatibilidad antes de cambiar la imagen; no soluciones una advertencia borrando el volumen.

### Datos de demostración en una base nueva

En una instalación nueva sin datos académicos puedes generar datos sintéticos con:

```powershell
docker compose exec web python manage.py generar_datos_sinteticos
```

El comando imprime las cuentas creadas. Para la institución Instituto Chimbarongo incluye `chimbarongo.docente1`, `chimbarongo.docente2`, `chimbarongo.alumno1` y `chimbarongo.admin`; la contraseña de demostración predeterminada es `EduGestor@123`. Estos usuarios son exclusivamente para desarrollo. Generar datos sintéticos no crea los índices curriculares ni configura claves de IA.

## Proveedores de IA

Desde **Registro de IA → Conexiones de IA** docentes y estudiantes pueden introducir una clave personal de Gemini o Qwen, el modelo de generación y, para Qwen, el endpoint de su región/workspace. **Guardar y comprobar clave** realiza una llamada JSON breve; solo guarda y selecciona la conexión si resulta correcta. **Usar Gemini/Qwen** también permite seleccionar una conexión existente desde esta página. No se cambia de proveedor ni de modelo cuando falla una conexión personal.

Las conexiones personales se guardan cifradas con Fernet en la sesión del servidor, vinculadas al usuario y a esa sesión. Caducan tras 8 horas; cerrar sesión las elimina de la sesión activa. Una conexión caducada o ilegible bloquea su clave hasta reconectarla o pulsar **Usar configuración del servidor**, para evitar consumir otra cuenta silenciosamente. Una clave nunca se devuelve en HTML, cookies ni logs. La comprobación consume cuota del proveedor; fuera de localhost se exige HTTPS.

El primer guardado genera `.ia-credentials.key` en el servidor, excluida de Git y del contexto de Docker. Debe conservarse como secreto junto al entorno; si se pierde, las conexiones personales deberán introducirse de nuevo. `IA_CREDENCIALES_ARCHIVO` permite ubicarla en almacenamiento privado persistente. Se requiere un backend de sesiones del servidor (el predeterminado es la base de datos); no se admite el de cookies firmadas. El formulario mantiene el modelo de embeddings administrado por el servidor, para preservar los índices existentes.

El modelo de generación se elige desde un desplegable independiente para Gemini y Qwen. Al abrir Registro de IA se consulta en segundo plano el catálogo oficial de la conexión actual. **Actualizar modelos** consulta con la clave y el endpoint introducidos, sin guardarlos ni cambiar el proveedor activo. El listado conserva la selección actual y filtra modelos dedicados a embeddings, voz, imagen o vídeo que no corresponden a estas herramientas. Qwen distingue modelos de texto y modelos que admiten imágenes según sus metadatos. El catálogo no acredita permisos ni todas las modalidades: el guardado sigue comprobando una respuesta JSON real.

La consulta se realiza en el servidor mediante [Gemini models.list](https://ai.google.dev/api/models#method:-models.list) y [Model Studio List models](https://docs.modelstudio.console.alibabacloud.com/en/model-studio/list-models), paginando cuando corresponde. Solo se envían identificadores/nombres públicos al navegador; las claves van en cabeceras al proveedor y no en URLs. La caché de metadatos dura 15 minutos y se separa por proveedor, clave y endpoint. Un fallo conserva el modelo actual. Para consultar un endpoint distinto se exige introducir su clave; no se reenvía automáticamente la clave guardada a otro workspace.

La configuración compartida y los comandos de indexación siguen usando `.env`, sin modificarlo desde el formulario. Nunca subas claves a Git:

```dotenv
GEMINI_API_KEY=
GEMINI_MODEL=gemini-flash-latest
GEMINI_EMBEDDING_MODEL=gemini-embedding-001
QWEN_API_KEY=
QWEN_BASE_URL=https://dashscope-intl.aliyuncs.com/compatible-mode/v1
QWEN_MODEL=qwen3.8-flash
QWEN_EMBEDDING_MODEL=text-embedding-v4
```

La clave Qwen debe pertenecer a Singapur para ese endpoint. Puedes configurar el dominio de workspace de Singapur que muestre Model Studio. Tras cambiar `.env`, recrea el servicio web (`docker compose up -d --force-recreate web`, conservando tu override si corresponde); un simple reinicio no actualiza las variables del contenedor.

El selector inferior del panel lateral de docentes/alumnos permite elegir Gemini o Qwen. Gemini es el valor inicial cuando está configurado. La preferencia queda en la sesión y cada formulario captura el proveedor de su operación. Cada trabajo captura también el modelo y la huella de la conexión; una conexión cambiada o caducada detiene el trabajo para evitar consumir otra cuenta. No hay cambio automático de Qwen a Gemini ni a modo simulado si una petición falla.

`IA_PROVEEDOR=simulado` es un modo explícito de desarrollo/pruebas que no llama a APIs. No acredita la calidad de una respuesta real.

## RAG y espacios vectoriales

El RAG curricular usa `DocumentoCurricular` y `FragmentoCurricular` en PostgreSQL/pgvector. El texto del PDF se fragmenta y se guarda también como JSON junto al documento, con metadatos y SHA-256. El JSON puede existir antes de que termine la indexación. Los PDF escaneados requieren OCR previo.

El campo `embedding` conserva los vectores Gemini actuales. Qwen utiliza `embedding_qwen` de 768 dimensiones, con su modelo y una huella del texto para detectar cambios. El tutor mantiene el JSON Gemini existente y añade un archivo Qwen independiente, ignorado por Git. Ninguna consulta Qwen compara vectores Gemini.

En una base nueva, indexa primero al menos un PDF curricular con el comando de la siguiente sección. En una base que ya contiene documentos curriculares, completa sus vectores Qwen y los del corpus del tutor con:

```powershell
docker compose exec web python manage.py reindexar_qwen
```

El comando guarda avances por lotes y puede reanudarse. Repetirlo no vuelve a pedir embeddings ya completos con el mismo modelo y texto. Requiere clave Qwen y PostgreSQL. El RAG curricular de Qwen exige completar los fragmentos de la asignatura y nivel consultados. El tutor comprueba su corpus por separado. El registro muestra la cobertura actual. Cambiar el modelo de embeddings invalida esa cobertura y requiere reindexar.

Para incorporar un PDF nuevo:

```powershell
docker compose exec web python manage.py indexar_documento_curricular /app/knowledge/programa-matematica-1-basico.pdf --titulo "Programa Matemática 1 básico" --asignatura "Matemática" --ciclo BASICA --nivel 1
```

Por defecto crea ambos vectores. `--solo-gemini` permite excluir Qwen explícitamente y deja su cobertura pendiente. El corpus del tutor y el curricular son distintos; el registro muestra las fuentes realmente recuperadas. El asistente docente comprueba la cobertura del curso y asignatura seleccionados.

## Registro de operaciones

En **Registro de IA** cada usuario ve solo sus operaciones: proveedor/modelo, estado, duración, tamaño y huella de entradas, tipo/tamaño/huella de archivos, fuentes públicas recuperadas y lectura inicial de alternativas. No se guardan prompts completos, claves, adjuntos ni respuestas libres del modelo en ese registro. Los registros de lectura no sustituyen la revisión docente ni representan razonamiento interno.

La IA transcribe respuestas. El docente confirma o ajusta las marcas y el backend conserva el cálculo determinista de puntaje y nota.

## Pruebas

```powershell
docker compose exec web python manage.py test colegio --noinput
```

Las pruebas usan respuestas simuladas y mocks. Las llamadas reales de generación, imágenes/PDF, tutoría e indexación requieren claves y validación adicional.

GitHub Actions ejecuta las mismas pruebas y comprueba que no falten migraciones, con Python 3.12 y un servicio PostgreSQL/pgvector. No requiere claves API ni realiza inferencia real. La configuración está en `.github/workflows/edugestor-tests.yml`, en la raíz del repositorio.

Fuentes de la integración: [API compatible Qwen](https://www.alibabacloud.com/help/en/model-studio/compatibility-of-openai-with-dashscope), [PDF](https://www.alibabacloud.com/help/en/model-studio/pdf-understanding), [JSON](https://www.alibabacloud.com/help/en/model-studio/qwen-structured-output), [embeddings](https://www.alibabacloud.com/help/en/model-studio/embedding-interfaces-compatible-with-openai).

Conexiones personales: [sesiones de Django](https://docs.djangoproject.com/en/6.0/topics/http/sessions/) y [cifrado Fernet](https://cryptography.io/en/latest/fernet/).
