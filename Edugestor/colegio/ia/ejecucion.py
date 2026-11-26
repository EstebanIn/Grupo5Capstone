"""Contexto por solicitud y trazabilidad sin prompts ni adjuntos persistidos."""
from contextlib import contextmanager
from contextvars import ContextVar
from hashlib import sha256
from time import monotonic

_proveedor = ContextVar('ia_proveedor', default=None)
_operacion = ContextVar('ia_operacion', default=None)

def proveedor_seleccionado():
    return _proveedor.get()

@contextmanager
def usar_proveedor(nombre):
    token = _proveedor.set(nombre)
    try:
        yield
    finally:
        _proveedor.reset(token)

def anotar(**datos):
    actual = _operacion.get()
    if actual is not None:
        actual.update(datos)


CLAVES_PRINCIPALES = ('archivos', 'huella_entrada', 'caracteres_entrada', 'caracteres_salida', 'lectura')


@contextmanager
def llamada_secundaria():
    """
    Llamadas de apoyo dentro de una misma operación (por ejemplo, sugerir el puntaje
    de una pregunta de desarrollo después de leer la hoja). Conservan la traza de la
    llamada principal (archivos, huella y lectura) y suman sus caracteres.
    """
    actual = _operacion.get()
    if actual is None:
        yield
        return
    respaldo = {clave: actual[clave] for clave in CLAVES_PRINCIPALES if clave in actual}
    try:
        yield
    finally:
        entrada = actual.get('caracteres_entrada', 0) if actual.get('huella_entrada') != respaldo.get('huella_entrada') else 0
        salida = actual.get('caracteres_salida', 0) if entrada else 0
        actual.update(respaldo)
        actual['caracteres_entrada'] = respaldo.get('caracteres_entrada', 0) + entrada
        actual['caracteres_salida'] = respaldo.get('caracteres_salida', 0) + salida
        actual['llamadas_secundarias'] = actual.get('llamadas_secundarias', 0) + 1


def anotar_error(error):
    actual = _operacion.get()
    if actual is not None:
        diagnostico = actual.get('diagnostico')
        if diagnostico and diagnostico.get('categoria') == 'ok':
            diagnostico['categoria'] = error.categoria

def anotar_fuentes(fragmentos):
    # Solo referencias del corpus público, nunca mensajes del usuario.
    anotar(fuentes=[{
        'titulo': str(f.get('titulo', 'Libro de Matemática'))[:250],
        'pagina': f.get('pagina'),
        'fragmento': str(f.get('texto', ''))[:500],
        'metodo': f.get('metodo_recuperacion', 'vectorial'),
        # Identificador y puntaje permiten revisar después por qué se eligió cada fragmento.
        'id': str(f.get('id', ''))[:80],
        'puntaje': next((round(float(f[k]), 4) for k in ('puntaje_bm25', 'similitud') if f.get(k) is not None), None),
    } for f in fragmentos[:6]])

def anotar_entrada(sistema, mensajes):
    textos = sistema + '\n' + '\n'.join(m.get('texto', '') for m in mensajes)
    archivos = [{'tipo': mime, 'bytes': len(datos), 'sha256': sha256(datos).hexdigest()}
                for m in mensajes for datos, mime in m.get('archivos', [])]
    anotar(enviada=True, caracteres_entrada=len(textos), huella_entrada=sha256(textos.encode()).hexdigest(), archivos=archivos)

@contextmanager
def registrar_operacion(usuario, proveedor, operacion):
    datos = {'estado': 'SIN_ENVIO', 'enviada': False, 'fuentes': [], 'archivos': [], 'lectura': []}
    token = _operacion.set(datos)
    inicio = monotonic()
    try:
        yield
    except Exception as error:
        from .proveedor import ErrorIA
        datos['estado'] = 'ERROR'
        datos.setdefault('detalle', str(error) if isinstance(error, ErrorIA) else 'No fue posible completar la operación.')
        raise
    finally:
        _operacion.reset(token)
        if datos['enviada'] or datos['estado'] == 'ERROR':
            from colegio.models import RegistroIA
            RegistroIA.objects.create(
                usuario=usuario, proveedor=proveedor, operacion=operacion[:100],
                modelo=datos.get('modelo', '')[:160], estado=datos['estado'],
                duracion_ms=round((monotonic()-inicio)*1000),
                caracteres_entrada=datos.get('caracteres_entrada', 0),
                caracteres_salida=datos.get('caracteres_salida', 0),
                huella_entrada=datos.get('huella_entrada', ''),
                archivos=datos['archivos'], fuentes=datos['fuentes'], lectura=datos['lectura'],
                detalle=datos.get('detalle', '')[:400],
                diagnostico=datos.get('diagnostico', {}),
            )
