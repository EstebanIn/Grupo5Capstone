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
from django.views.decorators.debug import sensitive_variables
from .configuracion import valor

logger = logging.getLogger(__name__)


class ErrorIA(Exception):
    """Falla al obtener una respuesta útil del modelo. El mensaje se muestra al usuario."""


def proveedor_activo():
    from .ejecucion import proveedor_seleccionado
    return proveedor_seleccionado() or getattr(settings, "IA_PROVEEDOR", "simulado")


def generar(sistema, mensajes, *, ejemplo, formato_json=False, temperatura=0.7):
    """
    sistema: instrucciones del asistente.
    mensajes: [{"rol": "usuario" | "modelo", "texto": str,
                "archivos": [(bytes, mime_type), ...] opcional (imágenes o PDF)}, ...]
    ejemplo: respuesta usada por el proveedor simulado (str, o dict si formato_json).
    Retorna str, o dict si formato_json.
    """
    from .ejecucion import anotar, anotar_entrada
    from .qwen import generar as generar_qwen
    proveedor = proveedor_activo()
    adaptadores = {"gemini": _generar_gemini, "qwen": generar_qwen}
    modelos = {"gemini": valor('gemini', 'model'), "qwen": valor('qwen', 'model'), "simulado": "simulado"}
    anotar(modelo=modelos.get(proveedor, ''))
    anotar_entrada(sistema, mensajes)
    try:
        if proveedor == 'simulado':
            texto = json.dumps(ejemplo, ensure_ascii=False) if formato_json else ejemplo
        elif proveedor in adaptadores:
            texto = adaptadores[proveedor](sistema, mensajes, formato_json, temperatura)
        else:
            raise ErrorIA('Proveedor de IA no reconocido.')
        resultado = _parsear_json(texto) if formato_json else texto.strip()
        if not resultado:
            raise ErrorIA('La IA no entregó contenido válido.')
        lectura = []
        if isinstance(resultado, dict) and isinstance(resultado.get('respuestas'), list):
            for item in resultado['respuestas'][:100]:
                if not isinstance(item, dict):
                    continue
                numero = item.get('pregunta')
                lectura.append({
                    'pregunta': numero if isinstance(numero, int) and 0 < numero <= 100 else None,
                    'marcada': item.get('marcada') if item.get('marcada') in ('A','B','C','D',None) else None,
                    'estado': item.get('estado') if item.get('estado') in ('respondida','en_blanco','multiple','ilegible','no_encontrada') else 'no_valido',
                })
        anotar(estado='OK', caracteres_salida=len(texto), lectura=lectura)
        return resultado
    except ErrorIA as error:
        anotar(estado='ERROR',detalle=str(error))
        raise
    except Exception:
        anotar(estado='ERROR',detalle='Error al procesar la respuesta del proveedor.')
        raise ErrorIA('No fue posible procesar la respuesta de la IA.') from None


@sensitive_variables()
def _generar_gemini(sistema, mensajes, formato_json, temperatura):
    from google import genai
    from google.genai import errors, types

    if not valor('gemini', 'api_key'):
        raise ErrorIA("Falta configurar GEMINI_API_KEY.")

    cliente = genai.Client(
        api_key=valor('gemini', 'api_key'),
        http_options=types.HttpOptions(
            timeout=int(valor('gemini', 'timeout') or 90) * 1000,
            # Sobrecarga temporal del modelo (503) o límite por minuto (429): reintentar con espera.
            retry_options=types.HttpRetryOptions(
                attempts=int(valor('gemini', 'intentos') or 3), initial_delay=2.0, max_delay=8.0, http_status_codes=[429, 500, 503],
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
    modelos = [valor('gemini', 'model'), *valor('gemini', 'modelos_respaldo')]
    for indice, modelo in enumerate(modelos):
        try:
            respuesta = cliente.models.generate_content(model=modelo, contents=contenidos, config=configuracion)
            from .ejecucion import anotar
            anotar(modelo=modelo)
            break
        except errors.ServerError as error:
            # Modelo saturado aun después de los reintentos: se prueba el siguiente.
            logger.warning("Gemini %s no disponible (%s)", modelo, error.code)
            if indice == len(modelos) - 1:
                raise ErrorIA("El servicio de IA está saturado en este momento. Intenta de nuevo en unos minutos.") from error
            continue
        except errors.ClientError as error:
            logger.error("Gemini rechazó la solicitud (modelo %s): HTTP %s", modelo, error.code)
            if error.code == 429 and indice < len(modelos) - 1:
                continue  # la cuota del nivel gratuito es por modelo: probar el de respaldo
            if error.code == 429:
                raise ErrorIA("Se alcanzó el límite de uso de la IA. Espera un minuto e intenta de nuevo.") from error
            # Modelo inexistente, key inválida o sin permisos: no se arregla reintentando.
            raise ErrorIA("El asistente de IA no está bien configurado. Avísale al administrador del sistema.") from error
        except Exception as error:  # red, timeout
            logger.warning("No se pudo contactar a Gemini; detalle omitido para proteger la solicitud")
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
