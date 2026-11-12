# Pruebas del asistente con sus claves

Las claves se introducen exclusivamente en **Registro de IA → Conexiones de IA**. No enviarlas por chat, capturas, archivos ni Git. Estas pruebas consumen la cuota de la cuenta seleccionada. La aprobación pedagógica sigue correspondiendo al docente.

## Preparación y comprobación

Iniciar esta rama en una instalación de prueba con PostgreSQL, Redis, web, worker y beat. Conservar `.env`, base e índices existentes; crear respaldo antes de migrar una instalación con datos. En Docker Compose local:

```powershell
docker compose up --build -d
docker compose ps
docker compose exec web python manage.py check
```

El worker y web deben compartir la clave de cifrado y la carpeta privada. En esta rama, `docker-compose.yml` monta la misma carpeta de aplicación para ambos. El servicio beat limpia los trabajos interrumpidos y los archivos caducados. Los adjuntos se guardan cifrados temporalmente, se eliminan al terminar y no se envían por Redis.

Entrar como docente, abrir Registro de IA, conectar **un proveedor** y elegir un modelo. Repetir después con el otro proveedor. La conexión queda cifrada en la sesión del servidor y caduca a las ocho horas. No cambiar de conexión ni cerrar sesión mientras espera un trabajo: se comprueba nuevamente al ejecutarlo. Ante una sesión caducada, volver a iniciar sesión y crear una nueva operación.

## Casos controlados

En la barra lateral, **Asistente IA** abre la portada; la flecha despliega **Tus documentos** y **Operaciones recientes**. Cada listado tiene su página y paginación. Solo aparecen los datos del docente conectado.

Al abrir un material en borrador, el editor muestra una hoja con formato y tres pestañas: **Explicación y ejemplos**, **Ejercicios** y **Solucionario docente**. Probar negrita, cursiva, estilo de párrafo, listas, deshacer y rehacer. Guardar y recargar para comprobar que se conserva lo editado, incluidas las tablas existentes. Las secciones que no se editan mantienen su texto original.

**Vista del estudiante** muestra los cambios actuales de explicación y ejercicios sin el solucionario. Comprobarlo antes de aprobar. La aprobación sigue exigiendo revisar la separación de respuestas. Si JavaScript no carga, siguen disponibles los campos de texto para guardar el borrador. Revisar también a 390 px y navegar las pestañas con las flechas del teclado.

| Caso | Acción | Resultado que debe comprobar |
|---|---|---|
| Material, Gemini | Elegir 4° básico/Matemática. Tema: multiplicación de tres dígitos por uno y división de dos dígitos por uno. Solicitar ejemplo resuelto de 124 × 3 y ejercicios 132 × 3 y 84 ÷ 4. | Proveedor y modelo correctos. Explicación con ejemplos; ejercicios sin respuestas; solucionario aparte. Revisar exactitud de 396 y 21. |
| Material, Qwen | Repetir el mismo caso con Qwen y el modelo elegido. Si no hay corpus del curso, elegir **Fuentes del material → Objetivo personalizado (sin fuentes)**. | Ver etapas y duración; resultado completo o error recuperable. El modo personalizado no consulta embeddings ni acredita un OA oficial. Revisar categoría, HTTP e identificador en Registro de IA. Una espera cercana a 91 s, por sí sola, no demuestra timeout. |
| RAG | Repetir material y rúbrica con fuentes indexadas para ese curso y proveedor. | Ver cobertura por asignatura/nivel y fuentes realmente recuperadas. Sin fuentes, el sistema identifica un objetivo personalizado; no acredita por sí solo un OA oficial. Qwen exige el índice curricular de ese nivel completo. |
| Rúbrica | Actividad: 124 × 3 y 84 ÷ 4 con bloques, dibujos o tabla permitidos. Pedir criterios de operación, representación de estrategia, cálculo y comprobación contextual. | Cada criterio tiene aprendizaje, evidencia y actividad. Escala 4–3–2–1, o 3–2–1; máximo y total calculados. Sin evidencia: 0 aparte. Descriptores concretos sin duplicación ni penalización por apoyos. |
| Revisión docente | Editar el borrador. Intentar aprobar una rúbrica sin confirmar sus cinco aspectos, luego revisarlos y aprobar. | La primera aprobación se detiene y conserva los campos. La aprobación final corresponde al docente. Un documento aprobado no se modifica; su actualización requiere copia editable. |
| PDF | Aprobar documentos revisados. Exportar estudiante y pauta docente. Usar también las vistas Imprimir. | A4 vertical, rúbrica horizontal, cabeceras y páginas. No se parten filas que caben completas. Verificar en el PDF estudiantil que no están las respuestas de ejercicios ni la pauta de pruebas; los ejemplos resueltos se conservan. |
| Material antiguo | Abrir material aprobado con pauta mezclada. | Se conserva el original; crear copia editable, separar secciones y revisar antes de habilitar su exportación estudiantil. |
| Revisión de prueba | Enviar una prueba para revisión con cada proveedor. | El POST registra un trabajo y la revisión queda recuperable al regresar. |
| Lectura de hoja | Subir una hoja sintética sin nombres ni RUT a una prueba aprobada. | Lectura asíncrona; revisar marcas en blanco, múltiples e ilegibles. Confirmar manualmente. La nota la calcula el servidor. |
| Recuperación | Salir de la pantalla y volver desde Operaciones recientes. Enviar dos veces el mismo formulario. | Se recupera el trabajo; el mismo envío no crea documentos duplicados. El estado se consulta cada 2 s, cada 15 s en segundo plano. |
| Error/reinicio | En una instalación de prueba, detener el worker durante una operación y volver a iniciarlo. | El trabajo no se vuelve a generar automáticamente si ya había empezado. Antes de cinco minutos queda recuperable como error; los temporales se limpian. |
| Aislamiento | Con dos docentes, intentar abrir la URL de trabajo, estado, impresión y descarga del otro. | 404/denegado; ninguna credencial, respuesta o archivo ajeno se muestra. |

Si se interrumpe la red o la lectura de Qwen, no reenviar inmediatamente: revisar el estado del trabajo y Registro de IA. Los reintentos automáticos se limitan a errores transitorios previos al contenido; nunca se cambia de proveedor o modelo para resolver un fallo. El límite total de generación Qwen es tres minutos y el trabajo tiene un límite de ejecución de cinco minutos.

## Respuesta que puede compartir sin claves

```text
Proveedor y modelo:
Herramienta y curso/asignatura:
Objetivo y actividad sintéticos:
Etapas observadas y duración:
Resultado: completado / error
Categoría y HTTP del Registro de IA (si corresponde):
¿Fuentes recuperadas del curso correcto?:
¿Separación de respuestas y PDF correctos?:
Observaciones pedagógicas:
```

Las pruebas de celular con red externa, computador apagado, reinicio de Oracle y respaldo remoto se ejecutarán después de crear las cuentas y la VM gratuita siguiendo `deploy/README.md`. Todavía no acreditan disponibilidad remota.

## Biblioteca curricular

Abrir **Asistente IA → Biblioteca curricular**, comprobar Matemática de 4° básico y buscar «multiplicación y división» con el curso correspondiente. Verificar título, páginas y enlace al PDF oficial. Generar un material en modo curricular con el proveedor elegido y comprobar las fuentes realmente recuperadas. El modo personalizado conserva su funcionamiento sin fuentes.

Comprobar nuevamente la fuente: un PDF idéntico no duplica documentos. Preparar el ZIP y descargar con el mismo docente; otro docente no debe poder consultar ese trabajo ni archivo. Para trasladar la biblioteca, seguir [biblioteca-curricular.md](biblioteca-curricular.md). La importación se ejecuta como operador, desde un paquete de confianza.
