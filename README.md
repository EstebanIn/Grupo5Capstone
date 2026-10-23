# Grupo5Capstone · EduGestor / InnovaGestor

Proyecto capstone de gestión escolar con asistentes de IA para docentes y estudiantes.

La aplicación ejecutable está en **[Edugestor/](Edugestor/)**. La **[guía de instalación y configuración](Edugestor/README.md)** explica Docker, cuentas de demostración, Gemini/Qwen, conexiones personales, RAG y pruebas.

```powershell
git clone https://github.com/EstebanIn/Grupo5Capstone.git
Set-Location Grupo5Capstone\Edugestor
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
docker compose up --build -d
```

Abre <http://127.0.0.1:8000/>. En una base nueva, sigue la guía para generar datos sintéticos y completar los índices antes de usar RAG.

`Fase 1/` y `Fase 2/` contienen entregables académicos. La aplicación incluida bajo las evidencias de Fase 2 es una copia histórica que difiere de `Edugestor/`; no se actualiza ni ejecuta automáticamente con esta integración.

Las claves API, la clave de cifrado de sesiones y los datos locales se mantienen fuera del cambio. El flujo de GitHub Actions comprueba migraciones y pruebas con PostgreSQL/pgvector, sin claves de proveedores.
