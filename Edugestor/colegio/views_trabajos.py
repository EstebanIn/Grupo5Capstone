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


@solo_rol('DOCENTE')
@require_POST
def exportar(request, pk):
    instrumento = get_object_or_404(InstrumentoIA, pk=pk, docente__usuario=request.user,
                                   institucion=request.institucion, estado='APROBADO')
    version = request.POST.get('version', 'estudiante')
    if version not in ('estudiante', 'docente'):
        return HttpResponse('Versión no válida.', status=400)
    try:
        from .ia.documentos import contenido_version
        contenido_version(instrumento, version)
        actual = crear_trabajo(request, 'exportar', {'version': version}, instrumento=instrumento)
    except ErrorIA as error:
        return HttpResponse(str(error), status=400)
    return respuesta_trabajo(request, actual)


@solo_rol('DOCENTE')
@never_cache
def descargar(request, pk):
    actual = propio(request, pk)
    if actual.estado != 'completado' or not actual.archivo:
        return HttpResponse('Archivo no disponible. Solicita una nueva exportación.', status=404)
    ruta = ruta_privada(actual.archivo)
    if not ruta.is_file():
        return HttpResponse('Archivo no disponible.', status=404)
    respuesta = FileResponse(ruta.open('rb'), as_attachment=True, filename=f'documento-{actual.pk}.pdf', content_type='application/pdf')
    respuesta['Cache-Control'] = 'private, no-store'
    respuesta['X-Content-Type-Options'] = 'nosniff'
    return respuesta


@solo_rol('DOCENTE')
@never_cache
def imprimir(request, pk, version):
    instrumento = get_object_or_404(InstrumentoIA, pk=pk, docente__usuario=request.user,
                                   institucion=request.institucion, estado='APROBADO')
    from .ia.documentos import contexto_documento
    try:
        contexto = contexto_documento(instrumento, version)
    except ErrorIA as error:
        return HttpResponse(str(error), status=400)
    return render(request, 'colegio/ia/documento.html', {**contexto, 'vista_impresion': True})


@solo_rol('DOCENTE')
@require_POST
def copiar(request, pk):
    from copy import deepcopy
    from django.shortcuts import redirect
    original = get_object_or_404(InstrumentoIA, pk=pk, docente__usuario=request.user, institucion=request.institucion)
    contenido = deepcopy(original.contenido)
    if original.tipo == 'MATERIAL':
        contenido = {'titulo': original.titulo, 'contenido': contenido.get('contenido', contenido.get('texto', '')),
                     'ejercicios': contenido.get('ejercicios', ''), 'solucionario': contenido.get('solucionario', ''),
                     'version_estructura': 2, 'separacion_revisada': False,
                     'fuentes': contenido.get('fuentes', []), 'rag_aplicado': contenido.get('rag_aplicado', False)}
    if original.tipo == 'RUBRICA':
        contenido.setdefault('puntajes', list(range(len(contenido['niveles']), 0, -1)))
    copia = InstrumentoIA.objects.create(docente=original.docente, carga=original.carga, tipo=original.tipo,
        titulo=original.titulo, objetivo=original.objetivo, parametros={**original.parametros, 'copia_de': original.pk},
        contenido_ia=deepcopy(original.contenido_ia), contenido=contenido)
    return redirect('ia_instrumento', pk=copia.pk)
