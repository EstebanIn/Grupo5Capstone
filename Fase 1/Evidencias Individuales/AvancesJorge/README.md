# EduGestor — guía de desarrollo local

Instrucciones para preparar EduGestor en Grupo5Capstone. Cada integrante trabaja con su propia base local y datos sintéticos.

## Requisitos

- Git.
- Python 3.12 o superior; se recomienda usar la misma versión en el equipo.
- Docker Desktop en ejecución para PostgreSQL 17.
- PowerShell en Windows o Bash/zsh en macOS y Linux.

## Clonar el repositorio

```bash
git clone https://github.com/EstebanIn/Grupo5Capstone.git
cd Grupo5Capstone
```

## Preparar Python

Desde la raíz del repositorio, entra en `Fase 1/Evidencias Individuales/AvancesJorge`.

### Windows (PowerShell)

```powershell
Set-Location 'Fase 1\Evidencias Individuales\AvancesJorge'
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Si PowerShell bloquea la activación, permite scripts solo durante la sesión actual y actívalo de nuevo:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

### macOS o Linux

```bash
cd "Fase 1/Evidencias Individuales/AvancesJorge"
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Las versiones están fijadas en `requirements.txt` para que todos instalen las mismas dependencias.

## Configurar y levantar PostgreSQL

Copia `.env.example` como `.env` dentro de `Proyecto_Sistema_Gestion_Escolar`. Si el `.env` ya existe, consérvalo y no lo sobrescribas.

PowerShell, desde `Fase 1/Evidencias Individuales/AvancesJorge`:

```powershell
$envFile = 'Proyecto_Sistema_Gestion_Escolar\.env'
if (-not (Test-Path $envFile)) {
    Copy-Item 'Proyecto_Sistema_Gestion_Escolar\.env.example' $envFile
}
```

macOS o Linux, desde `Fase 1/Evidencias Individuales/AvancesJorge`:

```bash
if [ ! -f Proyecto_Sistema_Gestion_Escolar/.env ]; then
  cp Proyecto_Sistema_Gestion_Escolar/.env.example Proyecto_Sistema_Gestion_Escolar/.env
fi
```

El ejemplo usa PostgreSQL local con base, usuario y contraseña `edugestor`, en el puerto `5432`. Son valores solo para desarrollo. Si el puerto está ocupado, cambia `POSTGRES_PORT` en el `.env`; Django y Docker leen ese mismo valor.

Entra al proyecto Django y levanta la base:

```bash
cd Proyecto_Sistema_Gestion_Escolar
docker compose up -d db
docker compose ps
```

Espera que el servicio `db` esté activo. Luego inicializa la base y carga los datos ficticios:

```bash
python manage.py migrate
python manage.py generar_datos_sinteticos
python manage.py runserver
```

Abre <http://127.0.0.1:8000/>. Mantén esa terminal abierta y el entorno virtual activo.

Ejecuta `generar_datos_sinteticos` una vez por base de datos. La opción `--limpiar` reemplaza datos que ya existan; úsala solo si quieres reiniciarlos.

Para apagar Django, presiona `Ctrl+C`. Para detener PostgreSQL y conservar el volumen:

```bash
docker compose stop db
```

## Alternativa: SQLite sin Docker

En el `.env`, deja `POSTGRES_DB` vacío (`POSTGRES_DB=`). Desde `Proyecto_Sistema_Gestion_Escolar` ejecuta:

```bash
python manage.py migrate
python manage.py generar_datos_sinteticos
python manage.py runserver
```

Django usará SQLite y creará un `db.sqlite3` local para ese integrante.

## Usuarios de demostración

El generador crea tres instituciones ficticias: Chimbarongo, Los Maitenes y El Almendro. Algunos usuarios de ejemplo son `chimbarongo.admin`, `maitenes.docente2` y `almendro.alumno1`. La contraseña inicial de las cuentas generadas es `EduGestor@123`.

## Asistentes IA

Sin `GEMINI_API_KEY`, los asistentes usan respuestas simuladas y no requieren una cuenta de Gemini. Para activar Gemini, agrega tu clave al `.env` de `Proyecto_Sistema_Gestion_Escolar` y reinicia Django:

```dotenv
GEMINI_API_KEY=tu_clave
```

No compartas ni subas `.env` o claves personales. El tutor envía a Gemini los mensajes ingresados y el corrector puede enviar imágenes o PDF de pruebas. Usa solo datos y pruebas sintéticos: la instrucción al modelo no impide transmitir los archivos al proveedor.

## Comprobaciones

Desde `Proyecto_Sistema_Gestion_Escolar`, con el entorno virtual activo:

```bash
python manage.py check
python manage.py test colegio
```

Las pruebas usan el proveedor simulado.

## Problemas frecuentes

- **No conecta a PostgreSQL:** confirma que Docker Desktop esté iniciado y que `docker compose ps` muestre activo el servicio `db`.
- **El puerto 5432 está ocupado:** cambia `POSTGRES_PORT` en el `.env` antes de iniciar Docker.
- **Falta un módulo de Python:** activa `.venv` desde `AvancesJorge` e instala con `pip install -r requirements.txt`.
- **No tienes clave de Gemini:** déjala sin configurar; el modo simulado sirve para desarrollo.

`runserver` es para desarrollo local, no para publicar el sistema en Internet.
