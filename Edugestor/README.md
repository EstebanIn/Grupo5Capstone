# Edugestor

Sistema de gestión escolar desarrollado con Django.

## Requisitos

- Git.
- Docker Desktop en ejecución.

No es necesario instalar Python ni crear un entorno virtual para ejecutar la aplicación con Docker.

## Preparar el proyecto

Desde PowerShell, clona el repositorio y entra a la carpeta:

    git clone https://github.com/EstebanIn/Grupo5Capstone.git
    Set-Location 'Grupo5Capstone\Edugestor'
    Copy-Item .env.example .env

Cada integrante debe crear su propio archivo local `.env` copiando **todo** el contenido de `.env.example` (el comando anterior hace la copia). Luego abre `.env` y pega la clave de Gemini que compartió el equipo en la línea `GEMINI_API_KEY=`, por ejemplo `GEMINI_API_KEY=TU_CLAVE`. No agregues comillas salvo que la clave las incluya. Guarda el archivo antes de iniciar Docker.

El `.env` normal contiene configuración local y está excluido de Git; nunca lo subas a GitHub. La clave se comparte entre integrantes solo por un canal privado. Sin una clave válida, los asistentes funcionan en modo simulado. Si ya están levantados los contenedores, aplica cambios de configuración recreando el servicio web con `docker compose up -d --force-recreate web`.

## Iniciar la aplicación y PostgreSQL

Con Docker Desktop abierto, ejecuta:

    docker compose up --build

La primera vez, Docker construye la imagen, inicia PostgreSQL y aplica las migraciones. Después abre http://127.0.0.1:8000/.

Para detener los contenedores, presiona Ctrl+C y luego ejecuta:

    docker compose down

Los datos de PostgreSQL se conservan en el volumen local edugestor_pgdata. No uses docker compose down -v si quieres conservarlos.

## Datos de prueba

En una base recién creada, puedes cargar datos sintéticos con:

    docker compose exec web python manage.py generar_datos_sinteticos

El comando avisa si la base ya contiene datos. No uses --limpiar a menos que quieras reemplazarlos.

## Asistentes de IA y privacidad

Sin GEMINI_API_KEY, la IA funciona en modo simulado. Cada integrante puede configurar su propia clave en su archivo local .env. No uses datos personales ni información real de estudiantes con los asistentes.

El servidor Django incluido es para desarrollo local; no lo uses para publicar el sistema en Internet.

