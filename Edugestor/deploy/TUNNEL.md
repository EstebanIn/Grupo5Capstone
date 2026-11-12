# Acceso temporal desde el computador propio

Este perfil mantiene Django, PostgreSQL/pgvector, Redis y Celery en el computador y ofrece una dirección HTTPS temporal de Cloudflare. Necesita el equipo encendido, Internet y Docker Desktop activo. No requiere una cuenta Cloudflare ni dominio comprado; no ofrece disponibilidad garantizada y la URL puede cambiar al reiniciar el túnel. No sustituye el despliegue independiente en Oracle descrito en [README.md](README.md).

El perfil versionado está en `config/tunnel.py`; desactiva DEBUG, usa Gunicorn y WhiteNoise, exige una clave Django privada, valida el hostname exacto, activa cookies seguras y CSRF HTTPS y evita caché de contenido privado. La elección personal de Gemini/Qwen y modelo prevalece sobre el valor predeterminado. Una sesión nueva requiere configurar su conexión personal desde Registro de IA y pulsar **Guardar y comprobar**; cambiar el selector exige pulsar **Aplicar**. El perfil remoto no utiliza respuestas simuladas.

## Preparación de otra instalación

Usar Docker Compose 2.24.4 o posterior. Preparar `.env`, usuarios y PostgreSQL según el README principal. No borrar volúmenes de una instalación existente. Desde `Edugestor/`, generar un archivo privado una sola vez:

```sh
python -c "from pathlib import Path; import secrets; p=Path('deploy/.env.tunnel'); p.open('x', encoding='utf-8').write('TUNEL_DJANGO_SECRET='+secrets.token_urlsafe(64)+'\nTUNEL_PUBLIC_HOST=pendiente.trycloudflare.com\nIA_PROVEEDOR=qwen\n')"
```

No se imprime la clave. El archivo está excluido de Git y del contexto Docker; custodiarlo con el archivo de cifrado de conexiones y el respaldo privado. La activación de una clave Django distinta requiere volver a iniciar sesión.

Aplicar migraciones, recopilar estáticos y arrancar el perfil seguro antes de abrir el túnel:

```sh
docker compose -f docker-compose.yml -f deploy/compose.tunnel.yml --env-file deploy/.env.tunnel run --rm web python manage.py migrate --noinput
docker compose -f docker-compose.yml -f deploy/compose.tunnel.yml --env-file deploy/.env.tunnel run --rm web python manage.py collectstatic --noinput
docker compose -f docker-compose.yml -f deploy/compose.tunnel.yml --env-file deploy/.env.tunnel up -d web worker beat tunnel
docker compose -f docker-compose.yml -f deploy/compose.tunnel.yml --env-file deploy/.env.tunnel logs --tail 60 tunnel
```

Copiar el hostname `*.trycloudflare.com` que entregue Cloudflare en `TUNEL_PUBLIC_HOST` de `deploy/.env.tunnel`. Esperar que terminen las operaciones activas y actualizar web/worker/beat sin detener la base:

```sh
docker compose -f docker-compose.yml -f deploy/compose.tunnel.yml --env-file deploy/.env.tunnel stop --timeout 310 web worker beat
docker compose -f docker-compose.yml -f deploy/compose.tunnel.yml --env-file deploy/.env.tunnel up -d --no-deps web worker beat
```

Abrir la dirección HTTPS seguida de `/login/`. La publicación es temporal y protege los documentos mediante el login y sus permisos; no compartir cuentas ni API keys. El puerto del origen queda limitado a loopback. Mantener un solo beat.

## Actualización y cierre

Antes de actualizar, crear y verificar un respaldo privado de PostgreSQL, clave de cifrado, configuración e índices/originales. Desplegar el commit validado, ejecutar `migrate` y `collectstatic`, esperar los trabajos en curso y recargar solo web/worker/beat. Conservar el contenedor `tunnel` evita cambiar la URL durante la actualización. Verificar login, POST, estado de trabajos y descarga; los tests simulados no sustituyen una generación real.

Para cerrar el acceso público, detener primero `tunnel`. Después se puede volver al perfil local siguiendo el README, conservando los volúmenes. Nunca activar el perfil de desarrollo mientras el túnel siga publicando el mismo origen.

En el equipo QA existente se conserva el proyecto aislado, puerto 8002 y sus rutas privadas; su configuración local importa este mismo perfil versionado. Las credenciales, los dumps, cookies, documentos personales y la dirección efímera no se publican en GitHub.

Referencia: [Cloudflare Quick Tunnels](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/).
