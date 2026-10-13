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

Cada integrante conserva su propio archivo .env. Ese archivo no se sube a GitHub. Sin GEMINI_API_KEY, los asistentes de IA funcionan en modo simulado. Para usar Gemini, configura tu clave personal en .env; no la compartas ni la subas al repositorio.

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
