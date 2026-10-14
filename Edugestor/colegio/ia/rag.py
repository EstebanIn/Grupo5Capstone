"""Embeddings y recuperación semántica del corpus curricular público."""

import logging
import math
import re
import time

from django.conf import settings
from django.db import connection
from django.db.models import Q
from pgvector.django import CosineDistance

from ..models import FragmentoCurricular
from .proveedor import ErrorIA

logger = logging.getLogger(__name__)
DIMENSIONES_EMBEDDING = 768


def _cliente_embeddings():
    if not settings.GEMINI_API_KEY:
        raise ErrorIA("Configura GEMINI_API_KEY para indexar o buscar documentos curriculares.")

    from google import genai

    return genai.Client(api_key=settings.GEMINI_API_KEY)


def crear_embeddings(textos, *, tipo):
    """Devuelve vectores Gemini de 768 dimensiones para documentos o consultas."""
    if not textos:
        return []
    if tipo not in ("RETRIEVAL_DOCUMENT", "RETRIEVAL_QUERY"):
        raise ValueError("Tipo de embedding no reconocido.")

    from google.genai import types

    cliente = _cliente_embeddings()
    vectores = []
    try:
        for inicio in range(0, len(textos), 16):
            for intento in range(6):
                try:
                    respuesta = cliente.models.embed_content(
                        model=settings.GEMINI_EMBEDDING_MODEL,
                        contents=textos[inicio:inicio + 16],
                        config=types.EmbedContentConfig(
                            task_type=tipo,
                            output_dimensionality=DIMENSIONES_EMBEDDING,
                        ),
                    )
                    break
                except Exception as error:
                    detalle = str(error)
                    es_limite_temporal = (
                        "429" in detalle or "RESOURCE_EXHAUSTED" in detalle
                    )
                    if not es_limite_temporal or intento == 5:
                        raise
                    espera = re.search(r"retry in ([0-9.]+)s", detalle, re.IGNORECASE)
                    segundos = float(espera.group(1)) + 1 if espera else min(5 * (2 ** intento), 60)
                    logger.warning(
                        "Gemini limitó los embeddings; reintento %s/5 en %.1f segundos",
                        intento + 1,
                        segundos,
                    )
                    time.sleep(segundos)
            for embedding in respuesta.embeddings or []:
                valores = [float(valor) for valor in embedding.values]
                if len(valores) != DIMENSIONES_EMBEDDING:
                    raise ErrorIA("Gemini devolvió un embedding con dimensión inesperada.")
                norma = math.sqrt(sum(valor * valor for valor in valores))
                if not norma:
                    raise ErrorIA("Gemini devolvió un embedding vacío.")
                vectores.append([valor / norma for valor in valores])
            time.sleep(0.75)
    except ErrorIA:
        raise
    except Exception as error:
        logger.exception("No se pudo crear embeddings curriculares en Gemini")
        raise ErrorIA(
            "No se pudieron generar los vectores del material curricular. Revisa la API key, cuota y conexión."
        ) from error

    if len(vectores) != len(textos):
        raise ErrorIA("Gemini no devolvió un vector por cada fragmento curricular.")
    return vectores


def buscar_fragmentos(*, consulta, asignatura, ciclo, nivel, limite=5):
    """Busca fragmentos relevantes, filtrando por asignatura y nivel escolar."""
    if connection.vendor != "postgresql":
        return []

    base = FragmentoCurricular.objects.filter(
        documento__activo=True,
        documento__asignatura__iexact=asignatura,
        documento__ciclo__in=(ciclo, ""),
    )
    base = base.filter(Q(documento__nivel=nivel) | Q(documento__nivel__isnull=True))
    if not base.exists():
        return []

    vector = crear_embeddings([consulta], tipo="RETRIEVAL_QUERY")[0]
    resultados = (
        base.annotate(distancia=CosineDistance("embedding", vector))
        .select_related("documento")
        .order_by("distancia")[:limite]
    )
    return [
        {
            "texto": fragmento.texto,
            "titulo": fragmento.documento.titulo,
            "url": fragmento.documento.fuente_url,
            "pagina": fragmento.pagina,
            "distancia": float(fragmento.distancia),
        }
        for fragmento in resultados
    ]
