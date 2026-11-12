"""Caso sintético para revisión docente y QA, sin atribuirle recuperación RAG."""
RUBRICA_MA04 = {
    'titulo': 'Multiplicación y división · 4° básico',
    'descripcion': 'Actividad: resolver 124 × 3 (cajas de semillas) y 84 ÷ 4 (reparto en bandejas). '
        'Registrar operación, una representación o estrategia, cálculo y una comprobación contextual. '
        'Se permiten bloques, dibujos y tabla de multiplicación. Referencias propuestas: MA04 OA 05 y MA04 OA 06; '
        'el docente debe contrastar la actividad completa y respuestas de ejemplo.',
    'niveles': ['Destacado', 'Logrado', 'En desarrollo', 'Inicial'],
    'criterios': [
        {'criterio': 'Modelar la situación con una operación',
         'aprendizaje': 'Relacionar grupos iguales y reparto equitativo con multiplicación o división.',
         'evidencia': 'Dos expresiones con los datos y la incógnita del problema.',
         'actividad': 'Antes de calcular, escribir 124 × 3 y 84 ÷ 4 a partir de los enunciados.',
         'descriptores': ['Relaciona cada dato e incógnita con la operación adecuada y distingue el papel de los grupos y sus tamaños.',
             'Escribe ambas operaciones adecuadas con sus datos; deja implícita la identificación de la incógnita.',
             'Representa correctamente una situación; en la otra confunde número de grupos y operación.',
             'Usa los datos en operaciones que no representan grupos iguales ni reparto equitativo.']},
        {'criterio': 'Representar una estrategia de resolución',
         'aprendizaje': 'Usar descomposición distributiva y descomposición del dividendo.',
         'evidencia': 'Representación o pasos que conservan las cantidades al descomponer.',
         'actividad': 'Mostrar 124 = 100 + 20 + 4 y 84 = 80 + 4, u otra estrategia válida.',
         'descriptores': ['Representa ambas descomposiciones y conecta sus partes con las operaciones parciales sin alterar el total.',
             'Descompone ambas cantidades y muestra operaciones parciales válidas, con un vínculo entre pasos implícito.',
             'Representa una descomposición válida; en la otra omite una parte de la cantidad.',
             'Propone particiones que cambian las cantidades originales y no permiten resolver las operaciones.']},
        {'criterio': 'Ejecutar los cálculos',
         'aprendizaje': 'Calcular productos de tres dígitos por uno y cocientes de dos dígitos por uno.',
         'evidencia': 'Operaciones parciales y resultados numéricos registrados.',
         'actividad': 'Calcular 124 × 3 y 84 ÷ 4 con la estrategia elegida.',
         'descriptores': ['Obtiene ambos resultados con cálculos parciales correctos y registro consistente del valor posicional.',
             'Obtiene ambos resultados con un desliz de registro que identifica y corrige en el procedimiento.',
             'Ejecuta los pasos de una operación; en la otra un error de cálculo parcial modifica el resultado.',
             'Los errores en productos o cocientes parciales impiden obtener ambos resultados.']},
        {'criterio': 'Interpretar y comprobar el resultado',
         'aprendizaje': 'Comprobar coherencia de productos y cocientes en problemas rutinarios.',
         'evidencia': 'Respuesta con unidad y comprobación por estimación o relación inversa.',
         'actividad': 'Responder semillas totales y semillas por bandeja; contrastar con estimación y 21 × 4.',
         'descriptores': ['Responde con las unidades pertinentes y comprueba cada resultado mediante estimación o relación inversa interpretada en el contexto.',
             'Responde con unidades y realiza una comprobación válida para cada resultado, dejando implícita su interpretación contextual.',
             'Interpreta una respuesta y la comprueba; en la otra omite unidad o usa una comprobación que no permite decidir coherencia.',
             'Las respuestas no identifican lo que se obtiene y las comprobaciones no se relacionan con las operaciones realizadas.']}
    ],
    'fuentes': [], 'rag_aplicado': False, 'objetivo_personalizado': True,
}
