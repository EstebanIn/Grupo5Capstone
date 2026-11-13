import uuid
from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from .models import FuenteBiblioteca, DocumentoCurricular, FragmentoCurricular
from .views_ia import solo_rol, _contexto_base
from .ia import biblioteca, dominio
from .ia.trabajos import crear_trabajo, respuesta_trabajo
from .ia.proveedor import ErrorIA


@solo_rol('DOCENTE')
@never_cache
def biblioteca_docente(request):
    biblioteca.limpiar_interrumpidas()
    cargas = dominio.cargas_docente(request.user.docente)
    carga = cargas.filter(pk=request.GET.get('carga')).first() if request.GET.get('carga', '').isdigit() else cargas.first()
    consulta = request.GET.get('q', '').strip()[:500]
    resultados = biblioteca.buscar_texto(consulta=consulta, asignatura=carga.asignatura.nombre_asignatura,
        ciclo=carga.curso.ciclo, nivel=carga.curso.nivel) if consulta and carga else []
    fuentes = []
    for f in FuenteBiblioteca.objects.filter(aprobada=True):
        documentos = list(f.documentos.filter(activo=True))
        buscables = len(biblioteca.filas_buscables(FragmentoCurricular.objects.filter(
            documento__activo=True, documento__fuente_biblioteca=f).select_related('documento')))
        fuentes.append({'fuente': f, 'documentos': documentos,
            'fragmentos': sum(d.fragmentos.count() for d in documentos), 'buscables': buscables, 'token': uuid.uuid4()})
    return render(request, 'colegio/ia/biblioteca.html', _contexto_base(request,
        fuentes=fuentes, cargas=cargas, carga=carga, consulta=consulta, resultados=resultados,
        metodo=settings.BIBLIOTECA_BUSQUEDA, automatica=settings.BIBLIOTECA_AUTOMATICA,
        exportable=DocumentoCurricular.objects.filter(activo=True, fuente_biblioteca__aprobada=True).exists(),
        idempotencia=uuid.uuid4()))


@solo_rol('DOCENTE')
@require_POST
def actualizar(request, pk):
    fuente = get_object_or_404(FuenteBiblioteca, pk=pk, aprobada=True)
    try:
        return respuesta_trabajo(request, crear_trabajo(request, 'biblioteca_sync', {'fuente': fuente.pk}))
    except ErrorIA as error:
        return HttpResponse(str(error), status=400)


@solo_rol('DOCENTE')
@require_POST
def exportar(request):
    try:
        return respuesta_trabajo(request, crear_trabajo(request, 'biblioteca_export', {}))
    except ErrorIA as error:
        return HttpResponse(str(error), status=400)
