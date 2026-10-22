
import json
from functools import lru_cache
from pathlib import Path

from django.conf import settings
from .retriever import buscar_chunks_relevantes


@lru_cache(maxsize=1)
def cargar_documentos_rag():
    ruta = (
        Path(settings.BASE_DIR)
        / "knowledge"
        / "procesados"
        / "libro_matematica_embeddings.json"
    )

    with ruta.open("r", encoding="utf-8") as archivo:
        documentos = json.load(archivo)

    if not isinstance(documentos, list) or not documentos:
        raise ValueError("El índice RAG está vacío o no es válido.")

    return documentos


def recuperar_contexto(pregunta, top_k=4):
    documentos = cargar_documentos_rag()

    resultados = buscar_chunks_relevantes(
        pregunta,
        documentos,
        top_k=top_k,
    )

    return resultados
