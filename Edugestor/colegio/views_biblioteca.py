import uuid
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from .models import FuenteBiblioteca, DocumentoCurricular, FragmentoCurricular
from .views_ia import solo_rol, _contexto_base
from .ia import biblioteca, biblioteca_gestion as gestion, dominio
from .ia.trabajos import crear_trabajo, respuesta_trabajo
from .ia.proveedor import ErrorIA

OPCIONES_VECTORES = (25, 50, 100)


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
    proponer = cargas.filter(pk=request.GET.get('proponer')).first() if request.GET.get('proponer', '').isdigit() else None
    return render(request, 'colegio/ia/biblioteca.html', _contexto_base(request,
        fuentes=fuentes, cargas=cargas, carga=carga, consulta=consulta, resultados=resultados,
        metodo=settings.BIBLIOTECA_BUSQUEDA, automatica=settings.BIBLIOTECA_AUTOMATICA,
        exportable=DocumentoCurricular.objects.filter(activo=True, fuente_biblioteca__aprobada=True).exists(),
        idempotencia=uuid.uuid4(),
        cobertura=gestion.cobertura_docente(cargas), carga_propuesta=proponer,
        mis_propuestas=FuenteBiblioteca.objects.filter(propuesta_por=request.user).order_by('-propuesta_fecha')[:10],
        vectores=gestion.estado_vectores(), opciones_vectores=OPCIONES_VECTORES,
        token_vectores=uuid.uuid4()))


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


@solo_rol('DOCENTE')
@require_POST
def proponer(request):
    """El docente propone una fuente oficial para uno de sus cursos; el administrador decide."""
    carga = dominio.cargas_docente(request.user.docente).filter(pk=request.POST.get('carga') or None).first()
    if carga is None:
        messages.error(request, 'Elige uno de tus cursos para la fuente.')
        return redirect('ia_biblioteca')
    try:
        fuente = gestion.proponer_fuente(request.user, carga, ficha_url=request.POST.get('ficha_url', ''),
                                         descarga_url=request.POST.get('descarga_url', ''),
                                         titulo=request.POST.get('titulo', ''))
    except ErrorIA as error:
        messages.error(request, str(error))
        return redirect(f"{_url('ia_biblioteca')}?proponer={carga.pk}#proponer")
    messages.success(request, f'Propuesta enviada: «{fuente.titulo}». Un administrador la revisará; '
                              'al aprobarla se descargará e indexará automáticamente.')
    return redirect(f"{_url('ia_biblioteca')}#mis-propuestas")


@solo_rol('DOCENTE')
@require_POST
def vectores(request):
    """Lote explícito de embeddings con el proveedor seleccionado (consume cuota)."""
    if request.ia_proveedor not in ('gemini', 'qwen'):
        messages.error(request, 'Selecciona Qwen o Gemini en «Proveedor de IA» para crear vectores.')
        return redirect('ia_biblioteca')
    try:
        maximo = int(request.POST.get('maximo', OPCIONES_VECTORES[0]))
    except ValueError:
        maximo = OPCIONES_VECTORES[0]
    if maximo not in OPCIONES_VECTORES:
        maximo = OPCIONES_VECTORES[0]
    try:
        return respuesta_trabajo(request, crear_trabajo(request, 'biblioteca_vectores', {'maximo': maximo}))
    except ErrorIA as error:
        messages.error(request, str(error))
        return redirect('ia_biblioteca')


def _url(nombre):
    from django.urls import reverse
    return reverse(nombre)


# ======================== ADMINISTRADOR ========================

def _es_admin(usuario):
    return usuario.is_authenticated and usuario.tipo_usuario == 'ADMIN'


@login_required
@never_cache
def admin_biblioteca(request):
    if not _es_admin(request.user):
        from .views import redireccionar_por_rol
        return redireccionar_por_rol(request.user)
    biblioteca.limpiar_interrumpidas()
    fuentes = FuenteBiblioteca.objects.select_related('propuesta_por', 'revisada_por')
    return render(request, 'colegio/panel_admin_biblioteca.html', {
        'propuestas': fuentes.filter(aprobada=False, estado=FuenteBiblioteca.ESTADO_PROPUESTA).order_by('propuesta_fecha'),
        'aprobadas': [{'fuente': f, 'fragmentos': FragmentoCurricular.objects.filter(
                           documento__activo=True, documento__fuente_biblioteca=f).count()}
                      for f in fuentes.filter(aprobada=True)],
        'rechazadas': fuentes.filter(estado=FuenteBiblioteca.ESTADO_RECHAZADA).order_by('-revisada_fecha')[:20],
    })


@login_required
@require_POST
def admin_biblioteca_revisar(request, pk):
    if not _es_admin(request.user):
        from .views import redireccionar_por_rol
        return redireccionar_por_rol(request.user)
    fuente = get_object_or_404(FuenteBiblioteca, pk=pk)
    accion = request.POST.get('accion')
    try:
        if accion == 'aprobar':
            if fuente.aprobada:
                raise ErrorIA('La fuente ya está aprobada.')
            gestion.aprobar_fuente(fuente, request.user, titulo=request.POST.get('titulo'),
                                   descarga_url=request.POST.get('descarga_url'))
            transaction.on_commit(lambda: _encolar_sincronizacion(request, fuente))
            messages.success(request, f'Fuente aprobada: «{fuente.titulo}». La indexación quedó en cola.')
        elif accion == 'indexar':
            if not fuente.aprobada:
                raise ErrorIA('Primero aprueba la fuente.')
            transaction.on_commit(lambda: _encolar_sincronizacion(request, fuente))
            messages.success(request, f'Indexación de «{fuente.titulo}» en cola.')
        elif accion == 'rechazar':
            gestion.rechazar_fuente(fuente, request.user, request.POST.get('motivo', ''))
            messages.success(request, f'Propuesta rechazada: «{fuente.titulo}».')
        else:
            raise ErrorIA('Acción no válida.')
    except ErrorIA as error:
        messages.error(request, str(error))
    return redirect('panel_admin_biblioteca')


def _encolar_sincronizacion(request, fuente):
    from .tasks import sincronizar_fuente
    try:
        sincronizar_fuente.apply_async(args=[fuente.pk], retry=False)
    except Exception:
        messages.warning(request, 'No se pudo conectar con la cola. Un docente puede pulsar '
                                  '«Comprobar e indexar fuente» en su Biblioteca curricular.')
