from django.http import JsonResponse, FileResponse, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from .models import TrabajoIA, InstrumentoIA
from .views_ia import solo_rol, _contexto_base
from .ia.trabajos import limpiar, ruta_privada, crear_trabajo, respuesta_trabajo, FORMULARIOS
from .ia.proveedor import ErrorIA


def propio(request, pk):
    return get_object_or_404(TrabajoIA, pk=pk, usuario=request.user, institucion=request.institucion)


def enlace_resultado(trabajo):
    if trabajo.estado != 'completado':
        return ''
    if trabajo.operacion == 'exportar':
        return reverse('ia_trabajo_descargar', args=[trabajo.pk]) if trabajo.archivo else ''
    if trabajo.operacion == 'lectura' and trabajo.instrumento_id:
        return reverse('ia_corregir_prueba', args=[trabajo.instrumento_id]) + '?trabajo=' + str(trabajo.pk)
    if trabajo.instrumento_id:
        return reverse('ia_instrumento', args=[trabajo.instrumento_id])
    return ''


@solo_rol('DOCENTE')
@never_cache
def trabajo(request, pk):
    limpiar()
    actual = propio(request, pk)
    reintentar = ''
    if actual.operacion in FORMULARIOS:
        reintentar = reverse(FORMULARIOS[actual.operacion]) + '?trabajo=' + str(actual.pk)
    elif actual.instrumento_id:
        ruta = 'ia_corregir_prueba' if actual.operacion == 'lectura' else 'ia_instrumento'
        reintentar = reverse(ruta, args=[actual.instrumento_id])
    return render(request, 'colegio/ia/trabajo.html', _contexto_base(request,
        trabajo=actual, resultado_url=enlace_resultado(actual), reintentar=reintentar))


@solo_rol('DOCENTE')
@never_cache
def estado(request, pk):
    limpiar()
    actual = propio(request, pk)
    fin = actual.terminado or timezone.now()
    return JsonResponse({'id': str(actual.pk), 'etapa': actual.estado, 'mensaje': actual.mensaje,
                         'duracion': max(0, int((fin-(actual.iniciado or actual.creado)).total_seconds())),
                         'actividad': actual.actividad, 'resultado_url': enlace_resultado(actual)})
