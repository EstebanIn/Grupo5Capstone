"""Conexiones personales cifradas en sesiones del servidor, nunca en cookies."""
import json
import os
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.views.decorators.debug import sensitive_variables

PROVEEDORES = ('gemini', 'qwen')
CLAVE_SESION = 'ia_conexiones'
VIGENCIA = 8 * 60 * 60
_configuraciones = ContextVar('ia_configuraciones', default=None)


def valor(proveedor, campo):
    personal = (_configuraciones.get() or {}).get(proveedor, {})
    if campo in personal:
        return personal[campo]
    return getattr(settings, proveedor.upper() + '_' + campo.upper(), '')


@contextmanager
def usar_configuraciones(configuraciones):
    token = _configuraciones.set(configuraciones)
    try:
        yield
    finally:
        _configuraciones.reset(token)


@sensitive_variables()
def _cifrador(*, crear=False):
    if settings.SESSION_ENGINE == 'django.contrib.sessions.backends.signed_cookies':
        raise ValueError('Se requieren sesiones almacenadas en el servidor.')
    ruta = Path(settings.IA_CREDENCIALES_ARCHIVO)
    if crear and not ruta.exists():
        try:
            descriptor = os.open(ruta, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            pass
        else:
            with os.fdopen(descriptor, 'wb') as archivo:
                archivo.write(Fernet.generate_key())
    return Fernet(ruta.read_bytes().strip())


@sensitive_variables()
def guardar_conexion(request, proveedor, configuracion):
    if proveedor not in PROVEEDORES:
        raise ValueError('Proveedor no válido.')
    if not request.session.session_key:
        request.session.create()
    datos = {'usuario': request.user.pk, 'sesion': request.session.session_key,
             'proveedor': proveedor, 'configuracion': configuracion}
    cifrado = _cifrador(crear=True).encrypt(json.dumps(datos).encode()).decode('ascii')
    conexiones = dict(request.session.get(CLAVE_SESION, {}))
    conexiones[proveedor] = cifrado
    request.session[CLAVE_SESION] = conexiones


@sensitive_variables()
def leer_conexiones(request):
    resultado = {}
    for proveedor, cifrado in request.session.get(CLAVE_SESION, {}).items():
        if proveedor not in PROVEEDORES:
            continue
        try:
            datos = json.loads(_cifrador().decrypt(cifrado.encode('ascii'), ttl=VIGENCIA))
            if (datos['usuario'] != request.user.pk or datos['sesion'] != request.session.session_key
                    or datos['proveedor'] != proveedor):
                raise ValueError
            configuracion = datos['configuracion']
            if not isinstance(configuracion, dict) or not configuracion.get('api_key'):
                raise ValueError
            resultado[proveedor] = configuracion
        except (OSError, ValueError, KeyError, TypeError, AttributeError, InvalidToken):
            # No usar otra clave de facturación silenciosamente si caduca la personal.
            resultado[proveedor] = {'api_key': '', 'caducada': True}
    return resultado


def quitar_conexion(request, proveedor):
    conexiones = dict(request.session.get(CLAVE_SESION, {}))
    conexiones.pop(proveedor, None)
    request.session[CLAVE_SESION] = conexiones


def estado_publico(proveedor):
    personal = (_configuraciones.get() or {}).get(proveedor)
    return {'nombre': proveedor, 'titulo': 'Google · Gemini' if proveedor == 'gemini' else 'Alibaba Model Studio · Qwen',
            'personal': personal is not None, 'caducada': bool(personal and personal.get('caducada')),
            'configurado': bool(valor(proveedor, 'api_key')), 'modelo': valor(proveedor, 'model'),
            'embedding': getattr(settings, proveedor.upper() + '_EMBEDDING_MODEL'),
            'base_url': valor(proveedor, 'base_url') if proveedor == 'qwen' else '',
            'verificada': personal.get('verificada', '') if personal else ''}
