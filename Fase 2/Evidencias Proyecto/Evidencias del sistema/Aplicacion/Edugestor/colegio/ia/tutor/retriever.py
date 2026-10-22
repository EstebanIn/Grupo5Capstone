import numpy as np

from .embeddings import generar_embedding


def similitud_coseno(vector_a, vector_b):
    """
    Calcula similitud coseno entre dos vectores.
    """

    a = np.array(vector_a, dtype=float)
    b = np.array(vector_b, dtype=float)

    denominador = np.linalg.norm(a) * np.linalg.norm(b)

    if denominador == 0:
        return 0.0

    return float(np.dot(a, b) / denominador)


def buscar_chunks_relevantes(
    pregunta,
    documentos_vectorizados,
    top_k=4
):
    """
    Busca los chunks más similares a la pregunta.
    """

    embedding_pregunta = generar_embedding(pregunta)

    resultados = []

    for documento in documentos_vectorizados:

        similitud = similitud_coseno(
            embedding_pregunta,
            documento["embedding"]
        )

        resultados.append({
            "id": documento["id"],
            "pagina": documento["pagina"],
            "texto": documento["texto"],
            "similitud": similitud
        })

    resultados.sort(
        key=lambda item: item["similitud"],
        reverse=True
    )

    return resultados[:top_k]