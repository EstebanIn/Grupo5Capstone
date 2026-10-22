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