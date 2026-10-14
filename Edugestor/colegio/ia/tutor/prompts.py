
"""
Prompts del Tutor Escolar RAG de EduGestor.
"""


def construir_prompt_tutor(pregunta, contexto):
    """
    Construye el mensaje del usuario con el contexto
    documental recuperado por el RAG.

    contexto: lista de fragmentos devueltos por
    recuperar_contexto().
    """

    fragmentos = []

    for documento in contexto:
        pagina = documento["pagina"]
        texto = documento["texto"]

        fragmentos.append(
            f"[Página {pagina}]\n{texto}"
        )

    contexto_documental = "\n\n".join(fragmentos)

    return f"""
CONTEXTO DOCUMENTAL DEL LIBRO DE MATEMÁTICA:

{contexto_documental}

PREGUNTA DEL ESTUDIANTE:
{pregunta}

INSTRUCCIONES:
- Utiliza el contexto documental proporcionado.
- Explica los conceptos de forma clara y sencilla.
- Adapta la respuesta al nivel escolar del estudiante.
- No inventes información que no esté respaldada.
- Si el contexto no contiene información suficiente,
  indícalo claramente.
- Cuando corresponda, menciona las páginas consultadas.
- Guía el aprendizaje mediante ejemplos y preguntas.
- No entregues directamente respuestas de evaluaciones.
"""
