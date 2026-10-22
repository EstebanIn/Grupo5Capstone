"""Embeddings de Gemini para el Tutor Escolar RAG de EduGestor.

El modelo y la dimensionalidad deben coincidir con los usados para indexar
los documentos. Este módulo no vuelve a indexar el corpus existente.
"""

import logging
import time

from django.conf import settings
from google import genai
from google.genai import errors, types

logger = logging.getLogger(__name__)

# NO modificar este modelo sin comprobar con cuál se creó el JSON existente.
MODELO_EMBEDDING = "gemini-embedding-001"
DIMENSION_EMBEDDING = 768
MAX_INTENTOS = 3

_cliente = None


class CuotaEmbeddingAgotada(RuntimeError):
    """La cuota diaria de embeddings está agotada; reintentar no ayudará."""


def obtener_cliente():
    global _cliente
    if _cliente is None:
        api_key = getattr(settings, "GEMINI_API_KEY", "")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY no está configurada.")
        _cliente = genai.Client(api_key=api_key)
    return _cliente


def _validar_texto(texto):
    if texto is None or not str(texto).strip():
        raise ValueError("No se puede generar embedding de un texto vacío.")
    return str(texto).strip()


def _codigo_error(error):
    """Compatibilidad con atributos de código utilizados por el SDK."""
    codigo = getattr(error, "code", None)
    if codigo is None:
        codigo = getattr(error, "status_code", None)
    try:
        return int(codigo)
    except (TypeError, ValueError):
        return None


def _cuota_diaria_agotada(error):
    detalle = str(error).lower()
    return any(
        identificador in detalle
        for identificador in (
            "embed_content_free_tier_requests",
            "embedcontentrequestsperdayperprojectpermodel",
            "requestsperday",
        )
    )


def _esperar_reintento(intento, codigo):
    espera = min((10 if codigo == 429 else 5) * (2 ** (intento - 1)), 30)
    logger.warning(
        "Gemini embeddings respondió HTTP %s. Reintento %s en %ss.",
        codigo, intento + 1, espera,
    )
    time.sleep(espera)


def generar_embeddings(textos, max_intentos=MAX_INTENTOS):
    """Genera un vector por texto. No regenera los embeddings del JSON."""
    if not textos:
        return []
    if max_intentos < 1:
        raise ValueError("max_intentos debe ser mayor o igual a 1.")

    textos = [_validar_texto(texto) for texto in textos]
    cliente = obtener_cliente()

    for intento in range(1, max_intentos + 1):
        try:
            respuesta = cliente.models.embed_content(
                model=MODELO_EMBEDDING,
                contents=textos,
                config=types.EmbedContentConfig(
                    output_dimensionality=DIMENSION_EMBEDDING,
                ),
            )
            embeddings = respuesta.embeddings or []
            if len(embeddings) != len(textos):
                raise RuntimeError(
                    "La cantidad de embeddings recibidos no coincide con los textos enviados."
                )
            vectores = []
            for embedding in embeddings:
                vector = embedding.values
                if not vector or len(vector) != DIMENSION_EMBEDDING:
                    raise RuntimeError(
                        f"Dimensión de embedding inesperada; se requieren {DIMENSION_EMBEDDING}."
                    )
                vectores.append(vector)
            return vectores

        except errors.ClientError as error:
            codigo = _codigo_error(error)
            if codigo == 429:
                if _cuota_diaria_agotada(error):
                    logger.warning("Cuota diaria de embeddings Gemini agotada.")
                    raise CuotaEmbeddingAgotada(
                        "La cuota diaria de embeddings de Gemini está agotada. "
                        "La búsqueda vectorial no está disponible temporalmente."
                    ) from error
                if intento < max_intentos:
                    _esperar_reintento(intento, codigo)
                    continue
                raise RuntimeError(
                    "Gemini limita temporalmente las solicitudes de embeddings."
                ) from error
            if codigo == 401:
                raise RuntimeError("Gemini rechazó la autenticación. Revisa GEMINI_API_KEY.") from error
            if codigo == 403:
                raise RuntimeError("Sin permisos para utilizar embeddings de Gemini.") from error
            if codigo == 404:
                raise RuntimeError(f"Modelo de embeddings no encontrado: {MODELO_EMBEDDING}") from error
            raise

        except errors.ServerError as error:
            codigo = _codigo_error(error)
            if codigo in (500, 502, 503, 504) and intento < max_intentos:
                _esperar_reintento(intento, codigo)
                continue
            raise RuntimeError("El servicio de embeddings Gemini no está disponible.") from error

        except (ConnectionError, TimeoutError) as error:
            if intento < max_intentos:
                _esperar_reintento(intento, "red")
                continue
            raise RuntimeError("No fue posible conectar con Gemini para generar embeddings.") from error

    raise RuntimeError("No fue posible generar embeddings.")


def generar_embedding(texto, max_intentos=MAX_INTENTOS):
    return generar_embeddings([texto], max_intentos=max_intentos)[0]
