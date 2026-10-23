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

def anotar_fuentes(fragmentos):
    # Solo referencias del corpus público, nunca mensajes del usuario.
    anotar(fuentes=[{
        'titulo': str(f.get('titulo', 'Libro de Matemática'))[:250],
        'pagina': f.get('pagina'),
        'fragmento': str(f.get('texto', ''))[:500],
        'metodo': f.get('metodo_recuperacion', 'vectorial'),
    } for f in fragmentos[:5]])

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
    except Exception:
        datos['estado'] = 'ERROR'
        datos.setdefault('detalle', 'No fue posible completar la operación.')
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
            )
