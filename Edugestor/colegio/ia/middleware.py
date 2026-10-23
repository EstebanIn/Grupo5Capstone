"""Selección por operación, aislada mediante ContextVar y registrada por usuario."""
from django.conf import settings
from django.urls import resolve
from django.http import HttpResponseBadRequest
from .ejecucion import usar_proveedor, registrar_operacion
from .configuracion import leer_conexiones, usar_configuraciones

class ProveedorIAMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        usuario = getattr(request, 'user', None)
        if not usuario or not usuario.is_authenticated:
            return self.get_response(request)
        nombre = request.POST.get('proveedor') or request.session.get('ia_proveedor') or settings.IA_PROVEEDOR
        if nombre not in ('gemini', 'qwen', 'simulado') or (nombre == 'simulado' and settings.IA_PROVEEDOR != 'simulado'):
            return HttpResponseBadRequest('Proveedor de IA no válido.')
        request.ia_proveedor = nombre
        request.ia_conexiones = leer_conexiones(request)
        with usar_configuraciones(request.ia_conexiones), usar_proveedor(nombre):
            es_operacion = request.method == 'POST' and request.path.startswith(('/panel/docente/asistente/', '/panel/alumno/tutor/'))
            if es_operacion:
                ruta = resolve(request.path).url_name
                etiquetas = {'ia_crear_prueba':'Generar prueba','ia_crear_rubrica':'Generar rúbrica','ia_crear_material':'Generar material','ia_revisar_prueba':'Revisar prueba','ia_corregir_prueba':'Leer hoja de respuestas','tutor_alumno':'Tutoría RAG'}
                with registrar_operacion(usuario, nombre, etiquetas.get(ruta, ruta or 'Operación IA')):
                    return self.get_response(request)
            return self.get_response(request)
