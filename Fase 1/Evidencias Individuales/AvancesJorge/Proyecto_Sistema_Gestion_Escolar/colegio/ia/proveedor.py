"""
Acceso al modelo de lenguaje.

Todo el sistema llama a generar(); ninguna otra parte importa el SDK de Gemini.
Con IA_PROVEEDOR = "simulado" (valor por defecto si no hay GEMINI_API_KEY, y
el que usan las pruebas) se devuelve la respuesta de ejemplo que entrega cada
asistente, sin llamar a la API.
"""

import json
import logging
import re

from django.conf import settings

logger = logging.getLogger(__name__)


class ErrorIA(Exception):
    """Falla al obtener una respuesta útil del modelo. El mensaje se muestra al usuario."""


def proveedor_activo():
    return getattr(settings, "IA_PROVEEDOR", "simulado")


def generar(sistema, mensajes, *, ejemplo, formato_json=False, temperatura=0.7):
    """
    sistema: instrucciones del asistente.
    mensajes: [{"rol": "usuario" | "modelo", "texto": str,
                "archivos": [(bytes, mime_type), ...] opcional (imágenes o PDF)}, ...]
    ejemplo: respuesta usada por el proveedor simulado (str, o dict si formato_json).
    Retorna str, o dict si formato_json.
    """
    if proveedor_activo() == "gemini":
        texto = _generar_gemini(sistema, mensajes, formato_json, temperatura)
    else:
        texto = json.dumps(ejemplo, ensure_ascii=False) if formato_json else ejemplo

    return _parsear_json(texto) if formato_json else texto.strip()


def _generar_gemini(sistema, mensajes, formato_json, temperatura):
    from google import genai
    from google.genai import errors, types

    if not settings.GEMINI_API_KEY:
        raise ErrorIA("Falta configurar GEMINI_API_KEY.")

    cliente = genai.Client(
        api_key=settings.GEMINI_API_KEY,
        http_options=types.HttpOptions(
            timeout=90_000,
            # Sobrecarga temporal del modelo (503) o límite por minuto (429): reintentar con espera.
            retry_options=types.HttpRetryOptions(
                attempts=3, initial_delay=2.0, max_delay=8.0, http_status_codes=[429, 500, 503],
            ),
        ),
    )
    contenidos = [
        types.Content(
            role="user" if mensaje["rol"] == "usuario" else "model",
            parts=[
                *(types.Part.from_bytes(data=datos, mime_type=mime) for datos, mime in mensaje.get("archivos", [])),
                types.Part.from_text(text=mensaje["texto"]),
            ],
        )
        for mensaje in mensajes
    ]
    configuracion = types.GenerateContentConfig(
        system_instruction=sistema,
        temperature=temperatura,
        response_mime_type="application/json" if formato_json else "text/plain",
    )
    modelos = [settings.GEMINI_MODEL, *settings.GEMINI_MODELOS_RESPALDO]
    for indice, modelo in enumerate(modelos):
        try:
            respuesta = cliente.models.generate_content(model=modelo, contents=contenidos, config=configuracion)
            break
        except errors.ServerError as error:
            # Modelo saturado aun después de los reintentos: se prueba el siguiente.
            logger.warning("Gemini %s no disponible (%s)", modelo, error.code)
            if indice == len(modelos) - 1:
                raise ErrorIA("El servicio de IA está saturado en este momento. Intenta de nuevo en unos minutos.") from error
            continue
        except errors.ClientError as error:
            logger.error("Gemini rechazó la solicitud (modelo %s): %s", modelo, error)
            if error.code == 429 and indice < len(modelos) - 1:
                continue  # la cuota del nivel gratuito es por modelo: probar el de respaldo
            if error.code == 429:
                raise ErrorIA("Se alcanzó el límite de uso de la IA. Espera un minuto e intenta de nuevo.") from error
            # Modelo inexistente, key inválida o sin permisos: no se arregla reintentando.
            raise ErrorIA("El asistente de IA no está bien configurado. Avísale al administrador del sistema.") from error
        except Exception as error:  # red, timeout
            logger.exception("No se pudo contactar a Gemini")
            raise ErrorIA("No se pudo contactar al servicio de IA. Revisa la conexión e intenta de nuevo.") from error

    if not respuesta.text:
        raise ErrorIA("La IA no entregó respuesta. Reformula la solicitud e intenta de nuevo.")
    return respuesta.text


def _parsear_json(texto):
    limpio = re.sub(r"^```(?:json)?\s*|\s*```$", "", texto.strip())
    try:
        return json.loads(limpio)
    except json.JSONDecodeError as error:
        raise ErrorIA("La IA entregó una respuesta con formato inválido. Intenta de nuevo.") from error
