"""Catálogos oficiales por proveedor y conexión. No ejecuta inferencia."""
import re
from urllib.parse import urlsplit

import httpx
from django.core.cache import cache
from django.utils import timezone
from django.utils.crypto import salted_hmac
from django.views.decorators.debug import sensitive_variables

from .forms_conexion import validar_endpoint
from .proveedor import ErrorIA

IDENTIFICADOR = re.compile(r'^[a-zA-Z0-9._:-]{1,160}$')
ESPECIALES_GEMINI = re.compile(r'(?:tts|image|audio|transcrib|live|robotics|computer-use|embedding|deep-research|nano-banana)', re.I)
VIGENCIA_CATALOGO = 15 * 60
MAX_PAGINAS = 10


def _recibir(respuesta, proveedor):
    if respuesta.status_code in (401, 403):
        raise ErrorIA('No se pudo consultar el catálogo de ' + proveedor + '. Revisa la clave, sus permisos y la región.')
    if respuesta.status_code == 429:
        raise ErrorIA('El proveedor limita las consultas del catálogo. Intenta nuevamente más tarde.')
    if respuesta.status_code != 200:
        raise ErrorIA('El catálogo de ' + proveedor + ' no está disponible en este momento.')
    datos = respuesta.json()
    if not isinstance(datos, dict):
        raise ValueError
    return datos


def _modelo(identificador, nombre, imagenes=None):
    if not isinstance(identificador, str) or not IDENTIFICADOR.fullmatch(identificador):
        return None
    return {'id': identificador, 'nombre': str(nombre or identificador)[:160], 'imagenes': imagenes}


def _gemini(cliente, clave):
    modelos = []
    pagina = ''
    vistos = set()
    for _ in range(MAX_PAGINAS):
        parametros = {'pageSize': 1000}
        if pagina:
            parametros['pageToken'] = pagina
        datos = _recibir(cliente.get('https://generativelanguage.googleapis.com/v1beta/models',
            headers={'x-goog-api-key': clave}, params=parametros), 'Gemini')
        for fila in datos['models']:
            identificador = fila.get('name', '').removeprefix('models/')
            if (not identificador.startswith('gemini-') or ESPECIALES_GEMINI.search(identificador)
                    or 'generateContent' not in fila.get('supportedGenerationMethods', [])):
                continue
            modelo = _modelo(identificador, fila.get('displayName'))
            if modelo:
                modelos.append(modelo)
        pagina = datos.get('nextPageToken')
        if not pagina:
            return modelos
        if not isinstance(pagina, str) or pagina in vistos:
            raise ValueError
        vistos.add(pagina)
    raise ErrorIA('El catálogo de Gemini no se completó. Actualízalo nuevamente.')


def _qwen(cliente, clave, base_url):
    endpoint = urlsplit(validar_endpoint(base_url))
    url = 'https://' + endpoint.netloc + '/api/v1/models'
    modelos = []
    recibidos = 0
    for pagina in range(1, MAX_PAGINAS + 1):
        datos = _recibir(cliente.get(url, headers={'Authorization': 'Bearer ' + clave},
            params={'providers': 'qwen', 'page_no': pagina, 'page_size': 100, 'language': 'en-US'}), 'Qwen')
        if datos.get('success') is False:
            raise ValueError
        salida = datos['output']
        filas = salida['models']
        if not isinstance(filas, list) or not isinstance(salida['total'], int):
            raise ValueError
        for fila in filas:
            capacidades = fila.get('capabilities') or []
            modalidades = fila.get('inference_metadata') or {}
            identificador = fila.get('model', '')
            if (fila.get('provider') != 'qwen' or not identificador.startswith('qwen')
                    or not any(c in capacidades for c in ('TG', 'Reasoning', 'VU'))
                    or 'Text' not in modalidades.get('response_modality', [])):
                continue
            modelo = _modelo(identificador, fila.get('name'),
                'Image' in modalidades.get('request_modality', []))
            if modelo:
                modelos.append(modelo)
        recibidos += len(filas)
        if recibidos >= salida['total']:
            return modelos
        if not filas:
            raise ValueError
    raise ErrorIA('El catálogo de Qwen no se completó. Actualízalo nuevamente.')


@sensitive_variables()
def listar_modelos(proveedor, *, api_key, base_url=''):
    if proveedor not in ('gemini', 'qwen'):
        raise ErrorIA('Proveedor no reconocido.')
    if not api_key:
        raise ErrorIA('Introduce una clave o conecta el proveedor para consultar sus modelos.')
    if proveedor == 'qwen':
        base_url = validar_endpoint(base_url)
    # La caché conserva solo metadatos públicos; ni clave ni URL con credenciales.
    identificador = salted_hmac('ia-catalogo-v1', proveedor + '\n' + base_url + '\n' + api_key).hexdigest()
    clave_cache = 'ia-modelos:' + identificador
    guardado = cache.get(clave_cache)
    if guardado is not None:
        return guardado
    try:
        with httpx.Client(timeout=12, follow_redirects=False) as cliente:
            modelos = _gemini(cliente, api_key) if proveedor == 'gemini' else _qwen(cliente, api_key, base_url)
        # Mantener el orden del catálogo y eliminar versiones duplicadas.
        unicos = {}
        for modelo in modelos:
            unicos.setdefault(modelo['id'], modelo)
        modelos = list(unicos.values())
        if not modelos:
            raise ErrorIA('El proveedor no devolvió modelos de generación adecuados para este selector.')
        resultado = {'proveedor': proveedor, 'modelos': modelos,
                     'actualizado': timezone.now().isoformat(timespec='seconds')}
        cache.set(clave_cache, resultado, VIGENCIA_CATALOGO)
        return resultado
    except ErrorIA:
        raise
    except Exception:
        raise ErrorIA('No se pudo leer el catálogo del proveedor. Se conserva el modelo que tenías seleccionado.') from None
