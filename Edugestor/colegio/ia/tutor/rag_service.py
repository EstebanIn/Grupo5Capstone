
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
    from colegio.ia.proveedor import proveedor_activo
    if proveedor_activo() == 'qwen':
        from colegio.ia.indice_qwen import documentos_tutor_qwen
        from colegio.ia.qwen import embeddings
        from .retriever import similitud_coseno
        documentos = documentos_tutor_qwen()
        vector = embeddings([pregunta], tipo='RETRIEVAL_QUERY')[0]
        resultados = [{**d, 'similitud':similitud_coseno(vector,d['embedding']), 'metodo_recuperacion':'vectorial_qwen'} for d in documentos]
        resultados.sort(key=lambda d:d['similitud'],reverse=True)
        return resultados[:top_k]
    documentos = cargar_documentos_rag()

    resultados = buscar_chunks_relevantes(
        pregunta,
        documentos,
        top_k=top_k,
    )

    return resultados
