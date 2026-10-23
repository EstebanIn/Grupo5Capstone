"""Adaptador REST OpenAI-compatible de Model Studio. Claves solo en servidor."""
import base64
import math
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
    try:
        with httpx.Client(timeout=int(valor('qwen', 'timeout') or 90), follow_redirects=False) as cliente:
            respuesta = cliente.post(url+'/'+ruta, headers={'Authorization': 'Bearer '+valor('qwen', 'api_key')}, json=cuerpo)
        if respuesta.status_code != 200:
            codigo = respuesta.status_code
            if codigo in (401, 403):
                raise ErrorIA('Qwen rechazó el acceso. Revisa la clave, los permisos y la región del endpoint.')
            if codigo == 429:
                raise ErrorIA('Qwen alcanzó su límite de uso. Intenta nuevamente más tarde.')
            raise ErrorIA('Qwen no pudo procesar la solicitud (HTTP %s). No se cambió de proveedor.' % codigo)
        return respuesta.json()
    except ErrorIA:
        raise
    except Exception:
        # No registrar excepciones HTTP: pueden contener claves, archivos o prompts.
        raise ErrorIA('No fue posible comunicarse con Qwen o interpretar su respuesta.') from None

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
