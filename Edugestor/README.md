# Edugestor

Edugestor es una plataforma de gestión escolar desarrollada con Django. Esta guía explica cómo descargarla, iniciarla y aportar documentos al corpus RAG. Está escrita para Windows y PowerShell.

## Antes de empezar

Necesitas conexión a Internet y:

1. **Git para Windows**, para descargar el proyecto: [descargar Git](https://git-scm.com/install/windows).
2. **Docker Desktop**, para ejecutar la aplicación y PostgreSQL: [instalar Docker Desktop en Windows](https://docs.docker.com/desktop/setup/install/windows-install/).

Instala ambos siguiendo sus asistentes con las opciones recomendadas. Abre Docker Desktop y espera a que indique que el motor está iniciado. Si Docker solicita configurar WSL 2 o reiniciar Windows, sigue sus indicaciones y vuelve a abrir Docker Desktop después del reinicio. Consulta la [guía oficial de instalación de WSL](https://learn.microsoft.com/windows/wsl/install) si necesitas ayuda.

No necesitas instalar Python ni crear un entorno virtual para ejecutar Edugestor con Docker.

## Primera ejecución en Windows

### 1. Abre PowerShell en la carpeta donde guardarás el proyecto

Abre el menú Inicio, escribe **PowerShell** y abre Windows PowerShell. Ve a la carpeta donde quieras guardar el repositorio; por ejemplo:

```powershell
Set-Location $HOME\Documents
```

### 2. Descarga el repositorio y entra a Edugestor

Ejecuta estos comandos una sola vez:

```powershell
git clone https://github.com/EstebanIn/Grupo5Capstone.git
Set-Location .\Grupo5Capstone\Edugestor
```

Si ya clonaste el repositorio, no repitas `git clone`. En PowerShell, entra a la carpeta `Edugestor` con la ruta donde lo guardaste; por ejemplo:

```powershell
Set-Location $HOME\Documents\Grupo5Capstone\Edugestor
```

Los siguientes comandos se ejecutan dentro de `Edugestor`, junto a este README y `docker-compose.yml`.

### 3. Crea tu configuración local

Copia el archivo de ejemplo solo si todavía no existe tu `.env`:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

La aplicación puede iniciarse sin una clave de Gemini; en ese caso, los asistentes de IA usan el modo simulado. Para usar Gemini, abre `.env`:

```powershell
notepad .env
```

Busca `GEMINI_API_KEY=` y pega tu clave después del signo `=`. Guarda y cierra el archivo. Cada integrante configura su propia clave. **No compartas ni subas `.env`; el repositorio ignora ese archivo.** Puedes crear o consultar tu clave en [Google AI Studio](https://aistudio.google.com/apikey).

### 4. Inicia Edugestor

Confirma que Docker Desktop siga abierto y ejecuta:

```powershell
docker compose up --build
```

La primera vez, Docker descarga componentes y construye la aplicación; puede tardar varios minutos. Cuando Django indique que inició en el puerto 8000, abre [http://127.0.0.1:8000/](http://127.0.0.1:8000/) en tu navegador. **Mantén abierta esta terminal mientras uses la plataforma.**

Para detenerla, vuelve a la terminal y presiona `Ctrl+C`. Después puedes cerrar los contenedores con:

```powershell
docker compose down
```

## Inicios posteriores

Abre PowerShell en la carpeta `Edugestor` y ejecuta:

```powershell
docker compose up
```

Para detenerla, presiona `Ctrl+C` y luego ejecuta `docker compose down`. La base PostgreSQL se conserva en el volumen local de Docker llamado `edugestor_pgdata`. No uses `docker compose down -v` si necesitas conservar esos datos.

## Comprobar el estado y resolver problemas

Desde otra ventana de PowerShell, entra también a `Edugestor` y ejecuta:

```powershell
docker compose ps
```

Si el servicio `web` no está activo, revisa sus mensajes:

```powershell
docker compose logs --tail 80 web
```

- **`docker` no se reconoce:** instala Docker Desktop y abre una nueva ventana de PowerShell.
- **Docker no está conectado:** abre Docker Desktop y espera a que el motor indique que está iniciado.
- **El navegador no abre la plataforma:** revisa `docker compose ps` y los mensajes de `web`.
- **Gemini responde `429 RESOURCE_EXHAUSTED`:** se agotó la cuota disponible para la API; espera el tiempo indicado por el mensaje de Gemini antes de volver a intentarlo.
- **Aparece un aviso de `fontTools` al leer un PDF:** ese aviso por sí solo no significa que la indexación haya fallado. Revisa el resultado final del comando.

## Datos de demostración (opcional)

En una base recién creada puedes cargar datos sintéticos para probar la plataforma:

```powershell
docker compose exec web python manage.py generar_datos_sinteticos
```

El comando avisa si la base ya contiene datos. Usa `--limpiar` solo si realmente quieres reemplazar los datos existentes por datos sintéticos.

## Corpus RAG y carpeta `knowledge`

RAG permite recuperar fragmentos relevantes de documentos curriculares para aportar contexto cuando Gemini genera contenido. Los PDF oficiales y los JSON extraídos se guardan en `knowledge` y se comparten con el equipo mediante Git.

Cada integrante usa una base PostgreSQL local e independiente. Al indexar un PDF, Edugestor:

1. Extrae texto de las páginas y guarda un JSON junto al PDF con sus metadatos y fragmentos.
2. Envía los fragmentos a Gemini para generar embeddings.
3. Guarda los textos y vectores en PostgreSQL/pgvector, en el volumen local `edugestor_pgdata`.

El JSON conserva el texto estructurado; los vectores viven en la base de datos. Por eso, al clonar el repositorio en otro computador, los documentos estarán en `knowledge`, pero cada persona debe indexarlos en su propia base para que el RAG pueda consultarlos allí.

### Indexar el programa de Matemática de 1° básico

Con Docker iniciado y `GEMINI_API_KEY` configurada en `.env`, ejecuta desde la carpeta `Edugestor`:

```powershell
docker compose exec web python manage.py indexar_documento_curricular /app/knowledge/programa-matematica-1-basico.pdf --titulo "Programa de Estudio Matemática 1° básico" --asignatura "Matemática" --ciclo BASICA --nivel 1 --version-documento 2024 --url https://www.curriculumnacional.cl/recursos/programa-estudio-matematica-1-basico
```

Un resultado que termina con `Indexado: ... fragmentos ... páginas` confirma que se guardaron los vectores. Si el comando indica que el PDF ya está indexado, no vuelve a duplicarlo en esa base. La detección compara el SHA-256 del archivo: un PDF idéntico se reconoce; si cambia el contenido, se considera un documento nuevo. Esta comprobación solo aplica a la base de datos donde se ejecutó el comando; las bases de los demás integrantes no se sincronizan entre sí.

El JSON se genera antes de solicitar los embeddings. Por eso, si la API falla o se agota la cuota, el JSON puede existir aunque los vectores todavía no estén indexados. Reintenta el comando cuando Gemini vuelva a estar disponible y confirma que aparezca el mensaje `Indexado:`.

Los PDF escaneados como imágenes requieren OCR antes de indexarlos. Usa fuentes oficiales y conserva los datos de título, asignatura, nivel, versión y URL al ejecutar el comando.