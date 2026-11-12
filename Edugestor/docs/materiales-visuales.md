# Apoyos visuales en los materiales

Los materiales nuevos pueden incluir diagramas didácticos junto a los ejemplos. El piloto de Matemática admite redondeo y ajuste, valor posicional, rectas para completar una decena o restar por complemento, arreglos de puntos, reparto exacto y barras de fracciones.

La IA propone datos y una ubicación, y el servidor calcula las operaciones y dibuja las figuras. No se ejecuta SVG/HTML del modelo ni se descargan imágenes externas al exportar. Son diagramas vectoriales propios, legibles al ampliar el PDF y utilizables en impresión en blanco y negro.

## Revisar un borrador

En el editor, abrir **Apoyos visuales del material**. Se puede proponer diagramas a partir de los ejemplos de redondeo, descomposición y completar decenas, sin llamar al proveedor; también añadir un diagrama, ajustar sus cantidades/título/sección y quitarlo al guardar.

Los diagramas aparecen dentro de la explicación, los ejercicios o el solucionario. El guardado conserva sus referencias aunque se edite el texto con formato. La vista del estudiante usa los mismos gráficos del material. El profesor debe comprobar que los ejemplos, diagramas y objetivo correspondan a su actividad antes de aprobar.

Para mejorar un material aprobado, usar **Crear copia editable** y trabajar sobre la copia. Los aprobados existentes no reciben ilustraciones automáticas ni se reescriben. La separación de ejercicios y solucionario sigue requiriendo revisión docente.

## Impresión y privacidad

Pantalla, impresión y PDF comparten los mismos diagramas. La versión estudiantil excluye los recursos del solucionario antes de renderizar. Los diagramas asignados a ejercicios dejan el resultado en blanco. Se mantienen los ejemplos resueltos que pertenecen a la explicación.

El PDF utiliza A4, encabezado institucional, numeración, tipografía legible y verde institucional. Las figuras se mantienen completas entre páginas. Se evitan títulos de sección duplicados y se agrupan referencias iguales conservando todas las páginas recuperadas. La numeración de las listas se conserva, incluso cuando empieza en una pregunta distinta de 1. Una muestra de un borrador se identifica como pendiente de aprobación.

## Verificación local

Se revisaron visualmente las versiones de estudiante/docente de una copia del material real de cálculo mental y una galería de los seis tipos. Se comprobó la resta 82−55 mediante los saltos 55→60→82, el ajuste 48+35, el reagrupamiento 402−187, los límites de los arreglos y el reparto sin soluciones en el documento estudiantil.

Se verificó por HTTPS la vista previa, el guardado con gráficos, escritorio de 1440 px y celular de 390 px sin desbordamientos ni errores JavaScript. Los tests cubren límites, cálculo en servidor, contenido escapado, ausencia de recursos externos, conservación de los originales aprobados, copias y eliminación de pautas antes de renderizar.

Las fotografías e ilustraciones libres no forman parte de este piloto; las figuras implementadas representan cantidades y estrategias del material. La estructura permite incorporar otros apoyos revisados posteriormente.
