"""
Gestión de la biblioteca curricular desde la interfaz.

- Cobertura: qué cursos del docente tienen fuentes listas para generar.
- Propuestas: un docente propone una fuente oficial de curriculumnacional.cl;
  solo un administrador la aprueba (y se indexa) o la rechaza.
- Vectores: estado de los embeddings opcionales por proveedor.
"""
import re
import uuid

from django.conf import settings
from django.db.models import Q
from django.utils import timezone
from django.utils.text import slugify

from colegio.models import FragmentoCurricular, FuenteBiblioteca
from .biblioteca import filas_buscables, fragmentos_scope, huella, url_autorizada
from .proveedor import ErrorIA

MAX_PROPUESTAS_PENDIENTES = 5
CICLOS = {'KINDER': 'Kínder', 'BASICA': 'básico', 'MEDIA': 'medio'}


def nombre_nivel(ciclo, nivel):
    if ciclo == 'KINDER':
        return 'Pre-kínder' if nivel == 1 else 'Kínder'
    return f"{nivel}° {CICLOS.get(ciclo, str(ciclo).lower())}"


def _legado(asignatura, ciclo, nivel):
    """Corpus anterior a la biblioteca (documentos sin fuente de catálogo), igual que rag.buscar_fragmentos."""
    return FragmentoCurricular.objects.filter(
        documento__activo=True, documento__fuente_biblioteca__isnull=True,
        documento__asignatura__iexact=asignatura, documento__ciclo__in=(ciclo, ''),
    ).filter(Q(documento__nivel=nivel) | Q(documento__nivel__isnull=True))


def _qwen_completo(base):
    modelo = settings.QWEN_EMBEDDING_MODEL
    return all(f.embedding_qwen is not None and f.modelo_embedding_qwen == modelo
               and f.huella_texto_qwen == huella(f.texto) for f in base.only(
                   'texto', 'embedding_qwen', 'modelo_embedding_qwen', 'huella_texto_qwen'))


def cobertura(*, asignatura, ciclo, nivel):
    """
    Estado de las fuentes para un curso y asignatura:
    lista | indexando | aprobada | error | propuesta | sin_fuente.
    """
    biblioteca = fragmentos_scope(asignatura=asignatura, ciclo=ciclo, nivel=nivel)
    total = biblioteca.count()
    if total:
        try:
            buscables = len(filas_buscables(biblioteca))
        except ErrorIA:
            buscables = 0
        return {'estado': 'lista', 'origen': 'biblioteca', 'fragmentos': total, 'buscables': buscables,
                'qwen': True}
    legado = _legado(asignatura, ciclo, nivel)
    total = legado.count()
    if total:
        return {'estado': 'lista', 'origen': 'anterior', 'fragmentos': total, 'buscables': total,
                'qwen': _qwen_completo(legado)}
    fuente = (FuenteBiblioteca.objects.filter(asignatura__iexact=asignatura, ciclo=ciclo, nivel=nivel)
              .exclude(estado=FuenteBiblioteca.ESTADO_RECHAZADA).order_by('-aprobada', '-pk').first())
    if fuente is None:
        return {'estado': 'sin_fuente'}
    if not fuente.aprobada:
        return {'estado': 'propuesta', 'fuente': fuente}
    if fuente.estado == 'actualizando':
        return {'estado': 'indexando', 'fuente': fuente}
    if fuente.estado == 'error':
        return {'estado': 'error', 'fuente': fuente}
    return {'estado': 'aprobada', 'fuente': fuente}


def cobertura_docente(cargas):
    """Una fila por asignatura y nivel (varias secciones comparten fuentes)."""
    filas = {}
    for carga in cargas.select_related('curso', 'asignatura'):
        asignatura, ciclo, nivel = carga.asignatura.nombre_asignatura, carga.curso.ciclo, carga.curso.nivel
        clave = (asignatura.lower(), ciclo, nivel)
        if clave not in filas:
            filas[clave] = {'asignatura': asignatura, 'ciclo': ciclo, 'nivel': nivel, 'carga': carga, 'token': uuid.uuid4(),
                            'nivel_nombre': nombre_nivel(ciclo, nivel), 'cursos': [],
                            **cobertura(asignatura=asignatura, ciclo=ciclo, nivel=nivel)}
        filas[clave]['cursos'].append(str(carga.curso))
    return sorted(filas.values(), key=lambda f: (f['estado'] == 'lista', f['ciclo'], f['nivel'], f['asignatura']))


def proponer_fuente(usuario, carga, *, ficha_url, descarga_url='', titulo=''):
    ficha_url = url_autorizada(str(ficha_url or '').strip())
    descarga_url = str(descarga_url or '').strip()
    if descarga_url:
        url_autorizada(descarga_url)
        if not re.search(r'\.pdf(?:\?|$)', descarga_url, re.I):
            raise ErrorIA('El enlace de descarga debe apuntar a un PDF.')
    if FuenteBiblioteca.objects.filter(ficha_url=ficha_url).exclude(estado=FuenteBiblioteca.ESTADO_RECHAZADA).exists():
        raise ErrorIA('Esa ficha ya está en el catálogo o tiene una propuesta pendiente.')
    if FuenteBiblioteca.objects.filter(propuesta_por=usuario, aprobada=False,
                                       estado=FuenteBiblioteca.ESTADO_PROPUESTA).count() >= MAX_PROPUESTAS_PENDIENTES:
        raise ErrorIA(f'Tienes {MAX_PROPUESTAS_PENDIENTES} propuestas pendientes. Espera la revisión del administrador.')
    asignatura, ciclo, nivel = carga.asignatura.nombre_asignatura, carga.curso.ciclo, carga.curso.nivel
    titulo = re.sub(r'\s+', ' ', str(titulo or '')).strip()[:250] or \
        f'Programa de Estudio {asignatura} · {nombre_nivel(ciclo, nivel)}'
    return FuenteBiblioteca.objects.create(
        slug=slugify(f'{asignatura}-{ciclo}-{nivel}')[:40] + '-' + uuid.uuid4().hex[:8],
        titulo=titulo, ficha_url=ficha_url, descarga_url=descarga_url,
        asignatura=asignatura, ciclo=ciclo, nivel=nivel,
        licencia='MINEDUC. Consultar condiciones de reutilización en la ficha y el documento original.',
        aprobada=False, automatica=False, estado=FuenteBiblioteca.ESTADO_PROPUESTA,
        mensaje='Propuesta por un docente; pendiente de revisión del administrador.',
        propuesta_por=usuario, propuesta_fecha=timezone.now())


def aprobar_fuente(fuente, administrador, *, titulo=None, descarga_url=None):
    if titulo is not None and titulo.strip():
        fuente.titulo = titulo.strip()[:250]
    if descarga_url is not None:
        descarga_url = descarga_url.strip()
        if descarga_url:
            url_autorizada(descarga_url)
        fuente.descarga_url = descarga_url
    fuente.aprobada, fuente.automatica = True, True
    fuente.estado, fuente.mensaje = 'pendiente', 'Aprobada por el administrador; indexación en cola.'
    fuente.revisada_por, fuente.revisada_fecha, fuente.motivo_rechazo = administrador, timezone.now(), ''
    fuente.proxima_revision = None
    fuente.save()
    return fuente


def rechazar_fuente(fuente, administrador, motivo):
    motivo = str(motivo or '').strip()[:300]
    if not motivo:
        raise ErrorIA('Indica el motivo del rechazo para el docente.')
    if fuente.aprobada:
        raise ErrorIA('La fuente ya fue aprobada.')
    fuente.estado, fuente.mensaje, fuente.motivo_rechazo = FuenteBiblioteca.ESTADO_RECHAZADA, f'Rechazada: {motivo}', motivo
    fuente.revisada_por, fuente.revisada_fecha = administrador, timezone.now()
    fuente.save()
    return fuente


def estado_vectores():
    """Fragmentos de la biblioteca con vector válido por proveedor (sin llamar a ninguna API)."""
    from .configuracion import valor
    base = FragmentoCurricular.objects.filter(documento__activo=True, documento__fuente_biblioteca__aprobada=True)
    total = base.count()
    resultado = []
    for proveedor, campo in (('qwen', 'embedding_qwen'), ('gemini', 'embedding')):
        try:
            modelo = str(valor(proveedor, 'embedding_model') or '')
        except Exception:
            modelo = ''
        listos = base.filter(**{f'{campo}__isnull': False, f'modelo_embedding_{proveedor}': modelo}).count() if modelo else 0
        resultado.append({'proveedor': proveedor, 'nombre': proveedor.capitalize(), 'modelo': modelo,
                          'listos': listos, 'total': total, 'pendientes': max(0, total - listos)})
    return resultado
