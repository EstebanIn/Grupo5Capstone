# Plan de mejora de la generación con IA

Origen: pruebas manuales con `qwen4-max` en 4° básico Matemática (prueba, rúbrica, material, revisión de prueba y corrección). El flujo funcionaba, pero la calidad dependía de que el docente detectara los errores. La aprobación pedagógica sigue siendo del docente.

## Fase 1. Errores confirmados (hecha)

| Problema observado | Cambio |
|---|---|
| Los espacios `___` desaparecían en el PDF | `markdown_seguro` los conserva; una línea solo de guiones bajos sigue siendo separador |
| Instrucción de los recuadros repetida | `instrucciones_prueba` quita las frases del modelo sobre recuadros y agrega una sola indicación |
| Claves C-A-D-B repetidas | `ordenar_alternativas` reparte la correcta entre A, B, C y D; alternativas solo numéricas quedan de menor a mayor. No se aplica en modo simulado |
| "1 puntos", ".." y una instrucción genérica | Plural correcto, filtros `con_punto`/`falta_punto` e instrucciones por tipo de documento |
| Rúbrica igual para estudiante y docente | Estudiante: sin el texto docente. Docente: registro de puntajes, total, tabla de evidencias y observaciones |
| Ficha de una página en 3 | Solo el tipo "Ficha visual" genera portada; figuras más compactas en el PDF |
| Fuentes en la versión del estudiante | Solo aparecen en la versión docente |

## Fase 2. OA oficial y fuentes (hecha)

- **Catálogo versionado** `knowledge/oa/matematica-4-basico.json`: los 27 OA de 4° básico con su texto oficial (lista de las págs. 44 a 46 del PDF) y 151 indicadores (tablas de cada unidad), revisados contra el PDF. Las páginas son del PDF, no la numeración impresa. El OA 11 tiene una nota: el PDF oficial trae erratas en sus ejemplos (`3/100 = 0,01`, `3/2 = 0,5`, `4,83 cm`).
- **Formularios**: el docente elige el OA oficial o un objetivo personalizado. Con OA, el campo de objetivo pasa a ser un foco opcional, y se valida que el OA corresponda al curso.
- **Generación**: con OA, su texto e indicadores son siempre la primera fuente de la IA (`curriculo.fragmento`), con la regla de no agregar contenidos de otros OA ni niveles. La búsqueda solo complementa, sin la lista completa de OA. La revisión de pruebas recibe el OA con sus indicadores.
- **Fuentes**: `biblioteca.es_general` excluye el aviso de lenguaje inclusivo, créditos e índice. El registro guarda id, método y puntaje de cada fragmento, y la interfaz dice "fuentes consultadas": consultarlas no prueba que respalden cada pregunta.
- **Documento oficial o personalizado**: `objetivo_personalizado` es falso solo si el docente eligió un OA del catálogo.

### Medir la búsqueda (sin consumir cuota)

```sh
docker compose exec web python manage.py evaluar_busqueda          # consulta con el OA
docker compose exec web python manage.py evaluar_busqueda --sin-oa # solo con el tema
```

Casos fijos con la página esperada del OA entre los 5 primeros resultados. Resultado al cerrar la fase 2: 8/8 en ambos modos y 0 páginas generales. Antes de excluirlas, "fracciones equivalentes" traía primero el aviso de lenguaje inclusivo (pág. 4).

La comparación con la búsqueda vectorial o híbrida queda pendiente: la consola necesita `QWEN_API_KEY` en el servidor para crear el vector de la consulta. Cambiar `BIBLIOTECA_BUSQUEDA` solo si mejora estos números.

## Pendiente

- **Fase 0**: repetir los casos de generación (3 corridas por caso, antes y después). Consume cuota.
- **Fase 3**: diseño por pregunta con indicador declarado, controles automáticos (figura mencionada y ausente, alternativas de igual valor, correcta más larga), figuras en las pruebas y pauta flexible.
- **Fase 4**: rúbrica, material y revisión (alineación no evaluada sin OA).
- **Fase 5**: corrección con observaciones del dibujo y medios puntos solo si la pauta los define; pruebas con hojas manuscritas y fotos.
- **Fase 6**: probar Biblioteca, Tutor, Registro de IA, descargas y copias.
- Catálogos de otros niveles: hay programas de 1° a 8° en `knowledge/`.
