# Validación local de la biblioteca curricular

Fecha: 12 de noviembre de 2026. Rama `codex/asistente-docente-cloudflare`. Esta evidencia corresponde a la revisión local previa a la publicación; se conservaron las modificaciones de interfaz/editor existentes en el checkout. La verificación posterior se registra en [validacion-publicacion.md](validacion-publicacion.md).

| Comprobación | Resultado observado |
|---|---|
| Migración `0024_biblioteca` sobre QA | Aplicada sin borrar instrumentos, sesiones ni conexiones. `makemigrations --check --dry-run`: sin cambios pendientes. |
| Suite completa Django | **178 pruebas correctas**, 152,976 segundos. `python manage.py test colegio --noinput`. Incluye 21 casos nuevos de biblioteca. |
| Programa oficial MINEDUC 4° básico | PDF real de 194 páginas y 6.470.798 bytes. SHA-256 `f3e86fd77c42c0e435e8aa1d77e96097af75256df03a84541f51e25a0c3ee232`. |
| Indexación automática real | 333 fragmentos con páginas. 289 habilitados para recuperación; se conservan y excluyen las tablas multinivel. No se usaron API keys. |
| Actualización desde navegador | Trabajo real de Celery completado. Mismo hash: no se duplicó ni volvió a extraer el corpus. |
| Exportación desde navegador | Trabajo real de Celery completado y descarga ZIP autenticada correcta. |
| Restauración del paquete real | Original y 333 fragmentos restaurados en una base temporal vacía. Integridad SHA-256, búsqueda y segunda importación idempotente comprobadas sin llamar a embeddings. |
| Interfaz | Edge, anchos 1440, 768 y 390 px. Sin desbordamiento horizontal ni errores JavaScript; capturas revisadas visualmente. |
| Persistencia preparada | Compose de producción validado con `config --no-env-resolution --quiet`; volumen de originales y respaldo `indices.tar` ampliados. |
| Seguridad y compatibilidad | Pruebas de dominio/redirecciones/tamaños, ZIP manipulado/rutas peligrosas, propietario, rol, fuentes aprobadas, lotes de vectores Qwen sin Gemini, reanudación y modelo incompatible correctas. |

La búsqueda usa texto local y conserva el proveedor/modelo de redacción elegido por el usuario. Las tablas de progresión mezclan columnas de varios cursos al extraer el PDF: se excluyen páginas completas de forma conservadora; esto no reemplaza la revisión del docente ni acredita un OA automáticamente.

Las pruebas de generación real con las claves personales de Gemini/Qwen quedan a cargo del usuario, según lo acordado. Este resultado acredita el entorno local de QA y la portabilidad del corpus. No acredita acceso remoto con el computador apagado, disponibilidad Oracle/Cloudflare ni restauración de un respaldo remoto de la aplicación completa.

Capturas: [escritorio](evidencias-biblioteca/biblioteca-1440.png), [celular](evidencias-biblioteca/biblioteca-390.png). Uso y traslado: [biblioteca-curricular.md](biblioteca-curricular.md).
