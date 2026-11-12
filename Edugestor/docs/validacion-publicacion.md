# Revisión para publicación y actualización local

Fecha: 12 de noviembre de 2026. Rama `codex/asistente-docente-cloudflare`, sobre `origin/main` `91ec381`. Se conservan los cinco commits iniciales y se añaden las mejoras probadas durante la revisión con el docente.

## Alcance revisado

- Trabajos persistentes Celery/Redis, recuperación, permisos por docente e institución y diagnóstico de Qwen por streaming.
- Interfaz verde y blanca, navegación paginada, editor de contenido, ejercicios y solucionario separados, y conservación de los campos ante errores.
- Biblioteca pública revisada de Matemática de 4° básico: descarga acotada, originales con hash, búsqueda textual local compartida por los módulos e importación/exportación portable. Los vectores opcionales conservan proveedor y modelo; las tablas multinivel se excluyen de la recuperación.
- Apoyos visuales matemáticos calculados en el servidor para pantalla, impresión y PDF, con edición de cantidades y ubicación. Las figuras del solucionario se excluyen de la versión estudiantil.
- Escalas y totales de rúbricas calculados en el servidor; revisión docente previa y fuentes realmente recuperadas.
- Fechas y horas mostradas en `America/Santiago`, manteniendo UTC en la base.
- Perfil HTTPS temporal versionado para el equipo de casa, sin respuestas simuladas, secretos en Git ni cambios a la instalación original.

## Evidencia comprobada antes de publicar

| Comprobación | Resultado |
|---|---|
| Suite completa Django/PostgreSQL | **201 pruebas correctas**, 173,787 segundos tras corregir el aislamiento de la cola; base temporal creada y eliminada. Incluye aislamiento de trabajos/archivos, biblioteca, editor, visuales, horarios y perfil del túnel. |
| Cloudflare Worker | **4 pruebas Node correctas**. Conservación de POST, cabeceras confiables, redirecciones y diagnóstico de caída. |
| Django | `manage.py check` sin incidencias; sin advertencia de directorio `static`. |
| Migraciones | `makemigrations --check --dry-run`: sin cambios. `migrate --plan`: sin operaciones pendientes en QA. La suite crea una base nueva hasta `0024_biblioteca`. |
| Dependencias | `pip check`: sin requisitos incompatibles. |
| Configuración de despliegue | Compose de producción y perfil de túnel válidos; la comprobación usa valores sintéticos y no activa infraestructura. |
| Biblioteca real | PDF oficial de 194 páginas; SHA-256 `f3e86fd77c42c0e435e8aa1d77e96097af75256df03a84541f51e25a0c3ee232`. 333 fragmentos, 289 recuperables. ZIP restaurado en base temporal con hash, búsqueda e idempotencia comprobados. |
| Editor y adaptación | Comprobaciones de navegador en escritorio y viewport de 390 px, sin desbordamiento horizontal ni errores JavaScript. |
| PDF | Muestras iniciales de pruebas, rúbrica y materiales largos renderizadas e inspeccionadas. Material visual: versión estudiantil y docente de cuatro páginas, figuras presentes y numeración de listas conservada. Los documentos del usuario permanecen fuera del repositorio. |
| Hora de Chile | Casos de verano, invierno y cambio de fecha correctos; comprobación HTTPS del Registro de IA sin modificar el instante original. |

La evidencia detallada anterior permanece en [validación inicial](validacion-asistente.md), [biblioteca](validacion-biblioteca.md) y [materiales visuales](materiales-visuales.md).

### Corrección detectada en GitHub Actions

La [primera ejecución publicada](https://github.com/EstebanIn/Grupo5Capstone/actions/runs/43315466734) pasó instalación, Django y migraciones, pero falló en dos de las 201 pruebas: idempotencia de trabajos y eliminación de adjuntos tras un error. Ambas compartían un auxiliar cuyo mock de `encolar` se cerraba antes de ejecutar los callbacks de commit. Esto intentaba contactar la cola real; el Redis local ocultaba la dependencia, mientras que CI no dispone de ese servicio para las pruebas unitarias.

Se corrigió el orden de los contextos para mantener el mock activo hasta terminar los callbacks. El auxiliar comprueba ahora que se simuló un único envío y que el trabajo sigue pendiente. Además, todas esas pruebas rechazan cualquier intento de llamar a `apply_async` sin reemplazarlo explícitamente. No se deshabilitaron pruebas, no se añadió Redis a CI para ocultar el fallo y no se modificó la cola de la aplicación.

## Publicación, despliegue y límites de aceptación

El docente confirmó que pudo generar con una IA real después de pulsar **Aplicar** en el selector de proveedor. Es evidencia comunicada por el usuario; no constituye una nueva ejecución automatizada independiente de Gemini y Qwen ni una aprobación pedagógica de todos los resultados. Sus claves personales no se extraen para las pruebas.

El destino autorizado es el equipo de casa con su túnel existente, conservando PostgreSQL, índices, originales, sesiones y clave de cifrado. El procedimiento contempla respaldo privado cifrado, imagen identificada por commit, migraciones, estáticos y reinicio de web/worker/beat sin recrear el túnel. La evidencia concreta de esa actualización se conserva localmente fuera de Git, sin datos privados en el PR.

Publicar la rama y abrir un PR no integra cambios en `main`. GitHub Actions verifica el código; no despliega la aplicación. El túnel depende del equipo encendido, Docker e Internet, y puede cambiar de URL al reiniciarse. No se provisionó Oracle ni se activaron servicios de pago. El despliegue independiente del computador, un respaldo diario fuera del equipo y su restauración remota siguen pendientes de preparar esa infraestructura.
