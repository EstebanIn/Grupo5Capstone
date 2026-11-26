from django.http import JsonResponse, FileResponse, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.db import transaction
import uuid
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
    if trabajo.operacion in ('exportar', 'biblioteca_export'):
        return reverse('ia_trabajo_descargar', args=[trabajo.pk]) if trabajo.archivo else ''
    if trabajo.operacion in ('biblioteca_sync', 'biblioteca_vectores'):
        return reverse('ia_biblioteca')
    if trabajo.operacion == 'revision':
        return ''
    if trabajo.operacion == 'mejora' and trabajo.instrumento_id:
        return reverse('ia_comparar_mejora', args=[trabajo.instrumento_id])
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
    if actual.operacion in ('biblioteca_sync', 'biblioteca_export', 'biblioteca_vectores'):
        reintentar = reverse('ia_biblioteca')
    elif actual.operacion == 'mejora':
        reintentar = reverse('ia_trabajo', args=[actual.parametros['revision']]) + '#aplicar-mejoras'
    elif actual.operacion in FORMULARIOS:
        reintentar = reverse(FORMULARIOS[actual.operacion]) + '?trabajo=' + str(actual.pk)
    elif actual.instrumento_id:
        ruta = 'ia_corregir_prueba' if actual.operacion == 'lectura' else 'ia_instrumento'
        reintentar = reverse(ruta, args=[actual.instrumento_id])
    return render(request, 'colegio/ia/trabajo.html', _contexto_base(request,
        trabajo=actual, resultado_url=enlace_resultado(actual), reintentar=reintentar,
        **_contexto_mejoras(actual)))


def _prueba_revisada(trabajo):
    """Prueba vinculada a una revisión terminada, si sigue existiendo."""
    if trabajo.operacion != 'revision' or trabajo.estado != 'completado' or not trabajo.instrumento_id:
        return None
    return InstrumentoIA.objects.filter(pk=trabajo.instrumento_id, docente__usuario=trabajo.usuario,
                                        tipo='PRUEBA').first()


def _contexto_mejoras(trabajo):
    if trabajo.operacion != 'revision' or trabajo.estado != 'completado':
        return {}
    from .ia.asistentes import secciones_revision
    prueba = _prueba_revisada(trabajo)
    return {'prueba_revisada': prueba, 'mostrar_mejoras': True,
            'secciones_mejora': secciones_revision(trabajo.resultado.get('revision', '')) if prueba else []}


@solo_rol('DOCENTE')
@require_POST
def aplicar_mejoras(request, pk):
    from django.contrib import messages
    from django.shortcuts import redirect
    from .ia.asistentes import secciones_revision
    revision = propio(request, pk)
    prueba = _prueba_revisada(revision)
    if not prueba:
        messages.error(request, 'Esta revisión no está vinculada a una prueba tuya. '
                                'Ábrela desde la prueba con «Revisar calidad con IA».')
        return redirect('ia_trabajo', pk=pk)
    validas = [s['clave'] for s in secciones_revision(revision.resultado.get('revision', ''))]
    elegidas = [c for c in validas if c in request.POST.getlist('secciones')]
    if not elegidas:
        messages.error(request, 'Elige al menos una observación para aplicar.')
        return redirect(reverse('ia_trabajo', args=[pk]) + '#aplicar-mejoras')
    try:
        actual = crear_trabajo(request, 'mejora', {'mejora_de': prueba.pk, 'revision': str(revision.pk),
                                                    'secciones': elegidas, 'objetivo': prueba.objetivo})
    except ErrorIA as error:
        messages.error(request, str(error))
        return redirect('ia_trabajo', pk=pk)
    return respuesta_trabajo(request, actual)


def _cambio(numero, original, mejorada):
    from .ia.asistentes import puntaje_pregunta
    return {'numero': numero, 'clave': f'p{numero}', 'original': original, 'mejorada': mejorada,
            'puntaje_original': puntaje_pregunta(original), 'puntaje_mejorada': puntaje_pregunta(mejorada)}


@solo_rol('DOCENTE')
@never_cache
def comparar_mejora(request, pk):
    """Compara la copia mejorada con la prueba original y deja elegir cambio por cambio."""
    from copy import deepcopy
    from django.contrib import messages
    from django.shortcuts import redirect
    from .ia.asistentes import cambios_prueba
    copia = get_object_or_404(InstrumentoIA, pk=pk, docente__usuario=request.user,
                              institucion=request.institucion, tipo='PRUEBA')
    original = InstrumentoIA.objects.filter(pk=copia.parametros.get('mejora_de'), docente=copia.docente).first()
    if not original or copia.estado != 'BORRADOR':
        return redirect('ia_instrumento', pk=copia.pk)
    # La propuesta de la IA se conserva para poder volver a elegir aunque ya se haya decidido una vez.
    base = copia.parametros.get('mejora_propuesta') or copia.contenido_ia
    cambios = cambios_prueba(original.contenido, base)
    preguntas = [_cambio(n, original.contenido['preguntas'][n - 1], base['preguntas'][n - 1])
                 for n in cambios if n != 'instrucciones']
    instrucciones = None
    if 'instrucciones' in cambios:
        instrucciones = {'original': original.contenido.get('instrucciones', ''),
                         'mejorada': base.get('instrucciones', '')}
    if request.method == 'POST':
        elegido = deepcopy(base)
        aceptadas = 0
        if instrucciones:
            if request.POST.get('instrucciones') == 'mejora':
                aceptadas += 1
            else:
                elegido['instrucciones'] = instrucciones['original']
        for cambio in preguntas:
            if request.POST.get(cambio['clave']) == 'mejora':
                aceptadas += 1
            else:
                elegido['preguntas'][cambio['numero'] - 1] = deepcopy(cambio['original'])
        copia.parametros = {**copia.parametros, 'mejora_propuesta': base, 'mejora_revisada': True}
        copia.contenido = elegido
        copia.contenido_ia = deepcopy(elegido)
        copia.save(update_fields=['parametros', 'contenido', 'contenido_ia'])
        messages.success(request, f'Se aplicaron {aceptadas} de {len(cambios)} cambios. Revisa el borrador '
                                  'antes de aprobarlo; la prueba original no se modificó.')
        return redirect('ia_instrumento', pk=copia.pk)
    return render(request, 'colegio/ia/comparar_mejora.html', _contexto_base(request,
        copia=copia, original=original, preguntas=preguntas, instrucciones=instrucciones,
        total_cambios=len(cambios)))


@solo_rol('DOCENTE')
@never_cache
def estado(request, pk):
    limpiar()
    actual = propio(request, pk)
    fin = actual.terminado or timezone.now()
    return JsonResponse({'id': str(actual.pk), 'etapa': actual.estado, 'mensaje': actual.mensaje,
                         'duracion': max(0, int((fin-actual.creado).total_seconds())),
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
    biblioteca = actual.operacion == 'biblioteca_export'
    respuesta = FileResponse(ruta.open('rb'), as_attachment=True,
        filename=f'biblioteca-{actual.pk}.zip' if biblioteca else f'documento-{actual.pk}.pdf',
        content_type='application/zip' if biblioteca else 'application/pdf')
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
@transaction.atomic
def copiar(request, pk):
    from copy import deepcopy
    from django.shortcuts import redirect
    original = get_object_or_404(InstrumentoIA.objects.select_for_update(), pk=pk, docente__usuario=request.user, institucion=request.institucion)
    try:
        token = str(uuid.UUID(request.POST.get('idempotencia', '')))
    except ValueError:
        token = str(uuid.uuid5(uuid.NAMESPACE_URL, str(request.session.session_key)+':copia:'+str(pk)))
    previa = InstrumentoIA.objects.filter(docente=original.docente, institucion=request.institucion,
        parametros__copia_de=original.pk, parametros__copia_token=token).first()
    if previa:
        return redirect('ia_instrumento', pk=previa.pk)
    contenido = deepcopy(original.contenido)
    if original.tipo == 'MATERIAL':
        contenido = {'titulo': original.titulo, 'contenido': contenido.get('contenido', contenido.get('texto', '')),
                     'ejercicios': contenido.get('ejercicios', ''), 'solucionario': contenido.get('solucionario', ''),
                     'version_estructura': 2, 'separacion_revisada': False,
                     'recursos_visuales': deepcopy(contenido.get('recursos_visuales', [])),
                     **({'ficha': deepcopy(contenido['ficha'])} if contenido.get('ficha') else {}),
                     'fuentes': contenido.get('fuentes', []), 'rag_aplicado': contenido.get('rag_aplicado', False)}
    if original.tipo == 'RUBRICA':
        contenido.setdefault('puntajes', list(range(len(contenido['niveles']), 0, -1)))
    copia = InstrumentoIA.objects.create(docente=original.docente, carga=original.carga, tipo=original.tipo,
        titulo=original.titulo, objetivo=original.objetivo, parametros={**original.parametros, 'copia_de': original.pk, 'copia_token': token},
        contenido_ia=deepcopy(original.contenido_ia), contenido=contenido)
    return redirect('ia_instrumento', pk=copia.pk)
