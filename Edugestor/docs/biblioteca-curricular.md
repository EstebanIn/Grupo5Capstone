# Biblioteca curricular persistente

La biblioteca guarda fuentes públicas aprobadas, originales PDF, fragmentos con página y vectores opcionales en PostgreSQL/pgvector y `knowledge/biblioteca/`. No entrena al modelo. Cada generación recibe únicamente los fragmentos recuperados para su asignatura, ciclo y nivel. Cambiar de computador o de API key no elimina el conocimiento guardado.

## Piloto y alcance

El catálogo inicial contiene el [Programa de Estudio Matemática de 4° básico del MINEDUC](https://www.curriculumnacional.cl/recursos/programa-estudio-matematica-4-basico), con su [PDF oficial](https://www.curriculumnacional.cl/614/articles-18979_programa.pdf). Es un programa curricular con orientaciones y ejemplos; no equivale a una colección completa de guías de estudiantes. Consultar las condiciones de reutilización indicadas en la ficha y en el original. No se atribuye una licencia abierta genérica a todos los recursos del portal.

Desde **Asistente IA → Biblioteca curricular** se puede actualizar la fuente, buscar en su texto por un curso propio y preparar una descarga portable. El profesor conserva la aprobación de sus instrumentos. Los campos de objetivo personalizados no se convierten en OA oficiales por haber recuperado una fuente.

La ficha oficial permite localizar el PDF del documento aprobado. Si la ficha no responde, se prueba su dirección PDF aprobada. No se rastrea indiscriminadamente Internet: ampliar a otros cursos/asignaturas exige revisar e incorporar una fuente al catálogo. No se incorporan respuestas, pautas, adjuntos ni materiales privados de docentes a esta biblioteca pública compartida entre instituciones.

Pruebas, rúbricas, materiales en modo curricular y tutor usan el mismo servicio. El tutor conserva su corpus legado cuando no hay biblioteca para su curso. El modo de material **objetivo personalizado** mantiene su elección explícita de generar sin fuentes. Los módulos de OCR y cálculo de calificaciones no necesitan consultar esta biblioteca.

## Instalación y actualización

Después de actualizar el código, ejecutar desde `Edugestor/`:

```sh
python manage.py migrate
python manage.py biblioteca_curricular sincronizar
```

En Docker, anteponer `docker compose exec app` (producción: servicio `web`). En el entorno QA aislado, ejecutar desde `qa-asistente/`: `docker compose -f compose.yml exec -T app python manage.py biblioteca_curricular sincronizar`.

Celery worker y **un solo** Celery beat deben estar activos. Beat comprueba cada hora si hay fuentes aprobadas pendientes; cada fuente disponible se revisa nuevamente tras siete días. Un fallo conserva la última versión y programa otro intento seis horas después. Un bloqueo con vencimiento de cinco minutos impide actualizaciones simultáneas y permite recuperación después de un reinicio. Un PDF idéntico no vuelve a extraerse ni pierde sus vectores. Las versiones anteriores permanecen guardadas, inactivas para las nuevas búsquedas.

Descargas exclusivamente HTTPS y dominios exactos autorizados, validando cada redirección. Límites por documento: 20 MiB, 400 páginas, tres millones de caracteres y 5.000 fragmentos. No se ejecutan scripts ni se recuperan recursos incrustados del PDF. PDF escaneado/protegido o sin texto suficiente exige revisión/OCR previa.

Configuración:

```dotenv
BIBLIOTECA_AUTOMATICA=true
BIBLIOTECA_BUSQUEDA=textual
# Directorio persistente para originales; no incluirlo en Git.
BIBLIOTECA_RAIZ=/app/knowledge/biblioteca
```

La búsqueda textual BM25 es el método inicial explícito y no usa embeddings ni API keys. Se registra como `textual_biblioteca`, sin inventar similitudes vectoriales. La redacción sigue utilizando el proveedor/modelo elegido y su cuota. No se promete que la biblioteca elimine errores o alucinaciones del modelo.

El programa incluye anexos de progresión entre cursos. Las páginas que contienen encabezados de varios niveles, o de un nivel distinto al documento, se excluyen conservadoramente de la recuperación para evitar mezclar columnas extraídas del PDF. Se preservan en el original y el corpus portable. La pantalla distingue fragmentos indexados de los habilitados para recuperar; el docente sigue comprobando la pertinencia de cada evidencia.

## Vectores opcionales y cuota

El operador puede generar lotes explícitos, con un máximo configurable de 1 a 200 fragmentos por ejecución. La clave se resuelve desde el entorno local; no se exporta. Cada lote guarda avances y omite vectores ya válidos por proveedor, modelo y huella del texto:

```sh
python manage.py biblioteca_curricular vectores --proveedor qwen --maximo 25
python manage.py biblioteca_curricular vectores --proveedor gemini --maximo 25
```

Repetir hasta procesar cero pendientes. Qwen no requiere una clave Gemini. Los vectores de ambos proveedores se guardan separados aunque tengan 768 dimensiones. Cambiar el modelo invalida su compatibilidad, sin borrar el otro índice. Con `BIBLIOTECA_BUSQUEDA=vectorial`, las consultas usan el proveedor seleccionado y exigen cobertura completa de ese curso; no cambian de proveedor ni método ante un error. Esta opción puede consumir cuota de embeddings. Reiniciar web/worker/beat tras cambios de configuración.

## Traslado a otro computador

Para usar una sola biblioteca desde varios dispositivos, conectarse a la misma instalación servidora. Para instalaciones independientes, exportar un paquete y transferirlo por un medio de confianza:

```sh
python manage.py biblioteca_curricular exportar --archivo biblioteca-v1.zip
# En el equipo de destino, con el mismo código/migraciones y PostgreSQL:
python manage.py migrate
python manage.py biblioteca_curricular importar --archivo biblioteca-v1.zip
```

La descarga web produce el mismo paquete en segundo plano; el archivo autenticado caduca a las 24 horas, accesible solo por su propietario e institución. Se puede volver a exportar. La importación se reserva al operador por CLI porque modifica fuentes públicas de todas las instituciones.

El ZIP versionado incluye originales públicos, clasificación, versión, procedencia/licencia, hashes SHA-256 y vectores compatibles. Excluye usuarios, sesiones, instituciones, claves, documentos del docente y pautas. Un hash detecta corrupción, no prueba autoría: importar únicamente paquetes de una instalación de confianza. El importador rechaza rutas peligrosas, enlaces, duplicados, archivos extra, tamaños excesivos, hashes incorrectos y fuentes no aprobadas en destino; vuelve a extraer el texto del original. Solo reutiliza vectores de modelo/dimensión/huella compatibles; los restantes quedan pendientes sin bloquear la búsqueda textual. Volver a importar es idempotente. No hay sincronización automática entre dos bases independientes.

## Persistencia y comprobación

Producción monta el volumen `biblioteca` para originales y mantiene metadatos/textos/vectores en PostgreSQL. `backup.sh` incluye originales y corpus legado en `indices.tar`; se deben restaurar tanto la base como ambos directorios en sus volúmenes. La exportación portable no sustituye el respaldo completo de documentos privados ni la configuración de la aplicación.

La suite `colegio.tests_biblioteca` comprueba actualización/idempotencia, conservación tras errores, bloqueos, filtrado curricular, cuatro módulos, Qwen sin Gemini, cuota por lotes, compatibilidad de vectores, permisos, descargas, integridad ZIP y restauración. Las pruebas de proveedores reales siguen a cargo del usuario con sus API keys. El despliegue remoto y la restauración fuera de la VM siguen pendientes hasta preparar la infraestructura.
