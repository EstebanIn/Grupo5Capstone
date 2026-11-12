# Acceso gratuito: preparación y activación

Arquitectura: navegador → Worker `workers.dev` → HTTPS/Caddy en Oracle → Gunicorn/Django. PostgreSQL/pgvector, Redis, Celery y beat quedan en la VM. El Worker transmite cuerpos y archivos sin transformar documentos. Esta carpeta prepara el despliegue; su presencia en GitHub no acredita una publicación real.

## Elegibilidad antes de crear recursos

En la región principal de la cuenta Oracle, comprobar etiqueta **Always Free Eligible**, consumo existente y capacidad de `VM.Standard.A1.Flex`. Configuración inicial: ARM64, **2 OCPU, 8 GB RAM y 50 GB de arranque**, Ubuntu ARM sin licencia de pago. No activar Pay As You Go ni usar créditos de prueba como requisito. Si no hay capacidad gratuita, detener el aprovisionamiento y esperar; no seleccionar otra forma de pago.

La [documentación Oracle](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm), consultada el 11-11-2026, publica 1.500 horas OCPU y 9.000 GB-hora mensuales, 200 GB de volúmenes compartidos y 20 GB de Object Storage para cuentas Always Free. La consola de la cuenta debe confirmar los cupos y el consumo restante. Las instancias inactivas pueden recuperarse: se ofrece continuidad mientras los recursos estén disponibles, sin garantía de disponibilidad.

Antes de provisionar, comprobar manifiestos y conservar el resultado:

```bash
docker buildx imagetools inspect python:3.12-slim
docker buildx imagetools inspect pgvector/pgvector:0.8.7-pg17-trixie
docker buildx imagetools inspect redis:7-alpine
docker buildx imagetools inspect caddy:2-alpine
```

Cada imagen debe incluir `linux/arm64`. El Dockerfile instala Pango y fuentes para WeasyPrint. Construir también la aplicación en ARM y ejecutar su suite antes de habilitar usuarios. Fijar los digest de los manifiestos verificados para la publicación concreta; no sustituir una imagen sobre un volumen PostgreSQL existente.

## Origen y dirección pública

1. Crear la VM gratuita confirmada, permitir SSH solo desde la IP administrativa y TCP 80/443 para HTTPS. No exponer 5432, 6379 ni 8000. Instalar Docker Compose desde su repositorio oficial y comprobar servicio al arrancar.
2. Crear un nombre DuckDNS y apuntarlo a la IP de la VM. Si la IP cambia, actualizar mediante su API con el token en un archivo privado, sin ponerlo en comandos de historial o logs. Confirmar DNS antes de Caddy. No se requiere un dominio comprado.
3. Clonar la rama en `/opt/edugestor`, entrar en `Edugestor`. Copiar `deploy/.env.production.example` a `deploy/.env.production`, modo 0600. Generar secretos distintos de al menos 32 caracteres para Django, PostgreSQL y el salto Worker–origen; introducirlos localmente sin publicarlos. Configurar el host completo `workers.dev` y el nombre DuckDNS. Conservar el modo simulado para el primer arranque.
4. En `deploy/cloudflare/wrangler.jsonc`, reemplazar ambos nombres. Con una cuenta **Workers Free**, usar Wrangler desde un entorno administrativo de confianza. Guardar el secreto con `wrangler secret put ORIGIN_SHARED_SECRET`; el valor debe coincidir con el origen. Revisar el código y ejecutar sus pruebas antes de `wrangler deploy`. No activar productos de pago.
5. Ejecutar desde `Edugestor/`:

```bash
docker compose --env-file deploy/.env.production -f deploy/compose.production.yml build
docker compose --env-file deploy/.env.production -f deploy/compose.production.yml up -d
docker compose --env-file deploy/.env.production -f deploy/compose.production.yml exec web python manage.py check --deploy
docker compose --env-file deploy/.env.production -f deploy/compose.production.yml exec web python manage.py generar_datos_sinteticos
```

Usar exclusivamente datos sintéticos y cambiar las contraseñas de demostración antes de abrir el acceso. No copiar `.env`, base, clave de cifrado ni índices de la instalación local. Indexar en esta nueva instalación las fuentes públicas autorizadas para cada proveedor y comprobar cobertura. Los volúmenes de credenciales, base e índices son persistentes. Nunca ejecutar `down -v` sobre el despliegue.

Caddy obtiene el certificado del nombre DuckDNS. Tanto Caddy como Django rechazan solicitudes sin el secreto de origen. Django confía en cabeceras de proxy únicamente después de esa comprobación; el Worker reemplaza las cabeceras recibidas, conserva sesiones y POST, no sigue redirecciones del origen y evita caché. Los archivos privados no tienen una ruta pública de estáticos.

`workers.dev` está [orientado a proyectos personales y académicos](https://developers.cloudflare.com/workers/configuration/routing/workers-dev/). [Workers Free permite 100.000 solicitudes por día](https://developers.cloudflare.com/workers/platform/limits/). Cada sondeo de progreso cuenta: 10 operaciones de tres minutos consumen aproximadamente 900 consultas. En segundo plano el sondeo baja a cada 15 segundos. Revisar también la cuota y costo de Gemini/Qwen en la cuenta seleccionada.

## Respaldos cifrados fuera de la VM

Crear un bucket **Standard Always Free** privado de OCI, con acceso S3 compatible. Confirmar los 20 GB compartidos y 50.000 peticiones mensuales en la cuenta; otras clases pueden tener condiciones diferentes durante una prueba o una cuenta de pago. Instalar restic en el host. La contraseña restic y las credenciales de objeto se custodian fuera de la VM y fuera de Git.

Crear `/etc/edugestor-backup.env` (0600, root) con `EDUGESTOR_ROOT=/opt/edugestor/Edugestor`, `RESTIC_REPOSITORY=s3:https://NAMESPACE.compat.objectstorage.REGION.oraclecloud.com/BUCKET`, `RESTIC_PASSWORD_FILE`, `AWS_ACCESS_KEY_ID` y `AWS_SECRET_ACCESS_KEY`. Inicializar el repositorio privado con `restic init` usando esas variables. El script guarda dump PostgreSQL (incluye documentos y vectores), índices JSON, clave de cifrado de conexiones, configuración y commit; restic los cifra antes de enviarlos. Los PDF regenerables y las fotos temporales no se respaldan. Ejecutar sin indexaciones concurrentes. La instalación local se conserva.

El límite local conservador de 9 GB evita ocupar todo el cupo, pero no mide otros buckets ni controla peticiones de la cuenta. Revisar ambos consumos en OCI antes de habilitar el timer. `backup.sh` conserva siete días y cuatro semanas; falla si el repositorio no está disponible o excede el presupuesto. Instalar los dos archivos systemd en `/etc/systemd/system/`, ajustar la ruta si procede y habilitar `systemctl enable --now edugestor-backup.timer` después de comprobar un primer respaldo.

## Restauración obligatoria antes de cerrar la aceptación

En otra carpeta privada, usar `restic restore latest --tag edugestor --target /RUTA-PRUEBA`. Encontrar los cuatro archivos del snapshot (la carpeta temporal queda dentro del árbol restaurado). Crear un proyecto Compose **diferente**, sin puertos públicos y con un volumen vacío. Restaurar `database.dump` con `pg_restore` en PostgreSQL 17/pgvector; restaurar clave e índices en sus volúmenes de prueba. Comparar conteos de instrumentos, documentos curriculares y fragmentos; comprobar lectura de un documento aprobado y de ambos índices. No restaurar sobre la VM de producción. Registrar snapshot, fecha, commit, conteos y resultado. Desactivar las claves de proveedores en la prueba y cambiar cuentas sintéticas si se publica una copia.

## Evidencia pendiente de infraestructura

Comprobar desde un celular con datos móviles: login, POST con CSRF, adjuntos y descarga de ambas versiones. Verificar que entrar directamente por DuckDNS devuelve 403, que no se cachean sesiones/documentos y que la dirección pública funciona con el computador local apagado. Reiniciar la VM y comprobar documentos e índices. Registrar los resultados y la restauración; un build o un push no sustituyen estas pruebas.
