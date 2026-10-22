"""Recuperador del Tutor Escolar RAG de EduGestor.

Prioriza similitud coseno entre embeddings compatibles. Si se agota la cuota
DIARIA de embeddings de Gemini, utiliza BM25 local sobre los mismos fragmentos.
No llama a Gemini al ejecutar ``buscar_chunks_bm25``.
"""

import logging
import math
import re
import unicodedata
from collections import Counter

import numpy as np

from .embeddings import CuotaEmbeddingAgotada, generar_embedding

logger = logging.getLogger(__name__)

PALABRAS_VACIAS = {
    "a", "al", "como", "con", "cual", "cuales", "de", "del", "el", "en",
    "es", "esta", "este", "esto", "la", "las", "lo", "los", "me", "mi",
    "para", "por", "que", "se", "son", "su", "sus", "un", "una", "y",
    "explica", "explicame",
}


def _tokens(texto):
    normalizado = unicodedata.normalize("NFKD", str(texto or "").lower())
    normalizado = "".join(c for c in normalizado if not unicodedata.combining(c))
    return [
        token for token in re.findall(r"[a-z0-9]+", normalizado)
        if len(token) > 1 and token not in PALABRAS_VACIAS
    ]


def similitud_coseno(vector_a, vector_b):
    """Devuelve similitud coseno, validando dimensiones y vectores nulos."""
    a = np.asarray(vector_a, dtype=float)
    b = np.asarray(vector_b, dtype=float)
    if a.ndim != 1 or b.ndim != 1 or a.shape != b.shape:
        raise ValueError("Los embeddings deben ser vectores 1D de igual dimensión.")
    denominador = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denominador == 0:
        return 0.0
    return float(np.dot(a, b) / denominador)


def buscar_chunks_bm25(pregunta, documentos_vectorizados, top_k=4):
    """Búsqueda textual local sobre ``texto``, sin API y sin usar embeddings."""
    if top_k <= 0:
        return []
    tokens_consulta = set(_tokens(pregunta))
    if not tokens_consulta or not documentos_vectorizados:
        return []

    corpus = [Counter(_tokens(doc.get("texto", ""))) for doc in documentos_vectorizados]
    longitudes = [sum(c.values()) for c in corpus]
    media = sum(longitudes) / len(longitudes) if longitudes else 1.0
    n = len(corpus)
    df = Counter()
    for frecuencias in corpus:
        df.update(t for t in tokens_consulta if t in frecuencias)

    resultados = []
    k1, b = 1.5, 0.75
    for doc, frecuencias, longitud in zip(documentos_vectorizados, corpus, longitudes):
        puntuacion = 0.0
        for termino in tokens_consulta:
            tf = frecuencias.get(termino, 0)
            if not tf:
                continue
            idf = math.log(1 + (n - df[termino] + 0.5) / (df[termino] + 0.5))
            puntuacion += idf * tf * (k1 + 1) / (
                tf + k1 * (1 - b + b * longitud / max(media, 1))
            )
        if puntuacion > 0:
            resultados.append({
                "id": doc.get("id"),
                "pagina": doc.get("pagina"),
                "texto": doc.get("texto", ""),
                "similitud": None,  # BM25 no es similitud coseno
                "puntaje_bm25": round(puntuacion, 5),
                "metodo_recuperacion": "bm25",
            })
    resultados.sort(key=lambda d: d["puntaje_bm25"], reverse=True)
    return resultados[:top_k]


def buscar_chunks_relevantes(pregunta, documentos_vectorizados, top_k=4):
    """Búsqueda vectorial y respaldo BM25 únicamente ante cuota diaria agotada."""
    if top_k <= 0 or not documentos_vectorizados:
        return []
    try:
        embedding_pregunta = generar_embedding(pregunta)
    except CuotaEmbeddingAgotada:
        logger.warning("Cuota diaria de embeddings agotada: activando respaldo BM25 local.")
        return buscar_chunks_bm25(pregunta, documentos_vectorizados, top_k=top_k)

    resultados = []
    for documento in documentos_vectorizados:
        similitud = similitud_coseno(embedding_pregunta, documento["embedding"])
        resultados.append({
            "id": documento.get("id"),
            "pagina": documento.get("pagina"),
            "texto": documento.get("texto", ""),
            "similitud": similitud,
            "metodo_recuperacion": "vectorial",
        })
    resultados.sort(key=lambda d: d["similitud"], reverse=True)
    return resultados[:top_k]
