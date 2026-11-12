"""Adaptador REST OpenAI-compatible de Model Studio. Claves solo en servidor."""
import base64
import math
import json
import re
import time
import threading
import httpx
from django.conf import settings
from django.views.decorators.debug import sensitive_variables
from django.core.exceptions import ValidationError
from .configuracion import valor
from .forms_conexion import validar_endpoint

@sensitive_variables()
def solicitar(ruta, cuerpo):
    from .proveedor import ErrorIA
    if not valor('qwen', 'api_key'):
        raise ErrorIA('Falta configurar QWEN_API_KEY en el servidor.')
    try:
        url = validar_endpoint(valor('qwen', 'base_url'))
    except ValidationError:
        raise ErrorIA('QWEN_BASE_URL debe ser un endpoint HTTPS de Model Studio terminado en /compatible-mode/v1.') from None
    from .ejecucion import anotar
    inicio = time.monotonic()
    limite = min(int(getattr(settings, 'QWEN_TOTAL_TIMEOUT', 180)), 180)
    diagnostico = {'categoria': 'respuesta_invalida', 'http': None,
                  'modelo': cuerpo.get('model', '')[:160], 'identificador': ''}
    timeout = httpx.Timeout(connect=settings.QWEN_CONNECT_TIMEOUT, read=settings.QWEN_READ_TIMEOUT,
                            write=30, pool=10)
    cliente = httpx.Client(timeout=timeout, follow_redirects=False)
    # El watchdog también interrumpe un flujo que nunca termina de enviar tokens.
    reloj = threading.Timer(limite, cliente.close)
    reloj.daemon = True
    reloj.start()
    try:
        for intento in range(2):
            if time.monotonic() - inicio >= limite:
                raise httpx.ReadTimeout('deadline')
            try:
                if ruta == 'chat/completions':
                    cuerpo = {**cuerpo, 'stream': True, 'stream_options': {'include_usage': True}}
                    with cliente.stream('POST', url+'/'+ruta, headers={'Authorization': 'Bearer '+valor('qwen', 'api_key')}, json=cuerpo) as respuesta:
                        diagnostico['http'] = respuesta.status_code
                        diagnostico['identificador'] = _identificador(respuesta.headers.get('x-request-id', ''))
                        if respuesta.status_code in (429, 503) and intento == 0:
                            time.sleep(1)
                            continue
                        _exigir_http(respuesta.status_code)
                        partes, terminado, final, uso = [], False, None, {}
                        longitud = 0
                        for linea in respuesta.iter_lines():
                            if time.monotonic() - inicio >= limite:
                                raise httpx.ReadTimeout('deadline')
                            if not linea.startswith('data:'):
                                continue
                            dato = linea[5:].strip()
                            if dato == '[DONE]':
                                terminado = True
                                break
                            if not dato:
                                continue
                            evento = json.loads(dato)
                            if 'error' in evento:
                                raise ErrorIA('Qwen interrumpió la respuesta. Revisa el trabajo antes de volver a intentar.')
                            diagnostico['identificador'] = _identificador(evento.get('id', '')) or diagnostico['identificador']
                            if evento.get('usage'):
                                uso = evento['usage']
                            for eleccion in evento.get('choices', []):
                                if eleccion.get('index', 0) != 0:
                                    continue
                                texto = (eleccion.get('delta') or {}).get('content') or ''
                                if not isinstance(texto, str):
                                    raise ValueError
                                longitud += len(texto)
                                if longitud > 2_000_000:
                                    raise ValueError
                                partes.append(texto)
                                final = eleccion.get('finish_reason') or final
                        if not terminado or final != 'stop' or not ''.join(partes).strip():
                            raise ErrorIA('Qwen entregó una respuesta incompleta. No se guardó ningún documento.')
                        resultado = {'choices': [{'message': {'content': ''.join(partes)}}], 'usage': uso}
                else:
                    respuesta = cliente.post(url+'/'+ruta, headers={'Authorization': 'Bearer '+valor('qwen', 'api_key')}, json=cuerpo)
                    diagnostico['http'] = respuesta.status_code
                    diagnostico['identificador'] = _identificador(respuesta.headers.get('x-request-id', ''))
                    if respuesta.status_code in (429, 503) and intento == 0:
                        time.sleep(1)
                        continue
                    _exigir_http(respuesta.status_code)
                    resultado = respuesta.json()
                diagnostico['categoria'] = 'ok'
                return resultado
            except (httpx.ConnectTimeout, httpx.ConnectError):
                if intento == 0:
                    continue
                raise
        raise ErrorIA('Qwen no pudo completar la solicitud.', categoria='conexion')
    except ErrorIA as error:
        diagnostico['categoria'] = error.categoria
        raise
    except httpx.TimeoutException:
        diagnostico['categoria'] = 'timeout'
        raise ErrorIA('Qwen superó el tiempo de espera. La operación no se repetirá automáticamente.', categoria='timeout') from None
    except (httpx.NetworkError, httpx.RemoteProtocolError):
        diagnostico['categoria'] = 'conexion'
        raise ErrorIA('Se interrumpió la conexión con Qwen. Revisa el estado antes de volver a intentar.', categoria='conexion') from None
    except Exception:
        if time.monotonic() - inicio >= limite:
            diagnostico['categoria'] = 'timeout'
            raise ErrorIA('Qwen superó el límite total de tres minutos.', categoria='timeout') from None
        raise ErrorIA('Qwen entregó una respuesta inválida. No se guardó el documento.') from None
    finally:
        reloj.cancel()
        cliente.close()
        diagnostico['duracion_ms'] = round((time.monotonic()-inicio)*1000)
        anotar(diagnostico=diagnostico)


def _identificador(valor_id):
    return valor_id[:120] if isinstance(valor_id, str) and re.fullmatch(r'[A-Za-z0-9_.:-]{1,120}', valor_id) else ''


def _exigir_http(codigo):
    from .proveedor import ErrorIA
    if codigo == 200:
        return
    categoria, mensaje = {
        401: ('autenticacion', 'Qwen rechazó la clave. Comprueba su región y vigencia.'),
        403: ('autenticacion', 'Qwen rechazó el acceso. Revisa permisos y región.'),
        404: ('modelo_no_disponible', 'El modelo Qwen seleccionado no está disponible en este endpoint.'),
        429: ('cuota', 'Qwen alcanzó el límite de uso. Intenta más tarde.'),
        503: ('no_disponible', 'Qwen está temporalmente saturado.'),
    }.get(codigo, ('solicitud_rechazada', 'Qwen rechazó la solicitud (HTTP %s).' % codigo))
    raise ErrorIA(mensaje, categoria=categoria)

def generar(sistema, mensajes, formato_json, temperatura):
    from .proveedor import ErrorIA
    if formato_json:
        sistema += '\nDevuelve únicamente JSON válido.'
    historial = [{'role': 'system', 'content': sistema}]
    for m in mensajes:
        partes = []
        for datos, mime in m.get('archivos', []):
            uri = 'data:'+mime+';base64,'+base64.b64encode(datos).decode('ascii')
            if mime == 'application/pdf':
                partes.append({'type': 'file', 'file': {'file_data': uri, 'filename': 'hoja.pdf'}})
            elif mime in ('image/jpeg', 'image/png', 'image/webp'):
                partes.append({'type': 'image_url', 'image_url': {'url': uri}})
            else:
                raise ErrorIA('Para Qwen usa imágenes JPG, PNG o WEBP, o un PDF. Convierte los archivos HEIC antes de enviarlos.')
        partes.append({'type': 'text', 'text': m['texto']})
        historial.append({'role': 'user' if m['rol'] == 'usuario' else 'assistant', 'content': partes})
    cuerpo = {'model': valor('qwen', 'model'), 'messages': historial, 'temperature': temperatura, 'include_tool_usage': True}
    if cuerpo['model'] in settings.QWEN_MODELOS_SIN_RAZONAMIENTO:
        cuerpo['enable_thinking'] = False
    if formato_json:
        cuerpo['response_format'] = {'type': 'json_object'}
    datos = solicitar('chat/completions', cuerpo)
    from .ejecucion import anotar
    paginas = (datos.get('usage') or {}).get('x_tools', {}).get('pdf_page_parser', {}).get('count')
    if isinstance(paginas, int) and paginas >= 0:
        anotar(detalle='Qwen informó lectura de %s páginas PDF.' % paginas)
    try:
        texto = datos['choices'][0]['message']['content']
        if not isinstance(texto, str) or not texto.strip():
            raise ValueError
        return texto
    except (KeyError, IndexError, TypeError, ValueError):
        raise ErrorIA('Qwen no entregó una respuesta de texto válida.') from None

def embeddings(textos, *, tipo):
    from .proveedor import ErrorIA
    if tipo not in ('RETRIEVAL_QUERY', 'RETRIEVAL_DOCUMENT'):
        raise ValueError('Tipo de embedding no reconocido.')
    resultado = []
    for inicio in range(0, len(textos), 10):
        lote = textos[inicio:inicio+10]
        respuesta = solicitar('embeddings', {'model': settings.QWEN_EMBEDDING_MODEL, 'input': lote, 'dimensions': 768, 'encoding_format': 'float'})
        try:
            filas = sorted(respuesta['data'], key=lambda f: f['index'])
            if [f['index'] for f in filas] != list(range(len(lote))):
                raise ValueError
            for fila in filas:
                vector = [float(v) for v in fila['embedding']]
                if len(vector) != 768 or not all(math.isfinite(v) for v in vector):
                    raise ValueError
                norma = math.sqrt(sum(v*v for v in vector))
                if not norma:
                    raise ValueError
                resultado.append([v/norma for v in vector])
        except (KeyError, TypeError, ValueError, OverflowError):
            raise ErrorIA('Qwen devolvió embeddings incompletos o de dimensión diferente de 768.') from None
    return resultado
