"""Biblioteca pública persistente: descarga acotada, versiones y búsqueda sin API."""
import hashlib
import io
import math
import os
import re
import time
import unicodedata
import uuid
from collections import Counter
from datetime import timedelta
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import httpx
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from pypdf import PdfReader

from colegio.models import DocumentoCurricular, FragmentoCurricular, FuenteBiblioteca
from .proveedor import ErrorIA

MAX_PDF = 20 * 1024 * 1024
MAX_FRAGMENTOS = 5000
HOSTS = {'www.curriculumnacional.cl', 'curriculumnacional.cl'}
VACIAS = set('a al como con cual de del el en es esta este la las lo los para por que se su sus un una y objetivo aprendizaje matematica basico estrategias describir'.split())


def huella(datos):
    return hashlib.sha256(datos if isinstance(datos, bytes) else datos.encode('utf-8')).hexdigest()


def url_autorizada(url):
    try:
        p = urlsplit(url)
        valida = (p.scheme == 'https' and p.hostname in HOSTS and p.port in (None, 443)
                  and not p.username and not p.password and not p.fragment)
    except ValueError:
        valida = False
    if not valida:
        raise ErrorIA('La fuente debe usar HTTPS en un dominio curricular autorizado.')
    return url


def descargar(url, *, maximo=MAX_PDF, plazo=None):
    """Valida cada salto, no usa proxies del entorno ni registra respuestas."""
    plazo = plazo or time.monotonic() + 90
    try:
        with httpx.Client(trust_env=False, timeout=httpx.Timeout(12, connect=5)) as cliente:
            for _ in range(4):
                url_autorizada(url)
                with cliente.stream('GET', url, headers={'User-Agent': 'EduGestor-Biblioteca/1.0'}) as r:
                    if r.is_redirect:
                        url = urljoin(url, r.headers.get('location', ''))
                        continue
                    r.raise_for_status()
                    contenido = bytearray()
                    for trozo in r.iter_bytes():
                        if time.monotonic() > plazo:
                            raise ErrorIA('La descarga curricular superó su tiempo máximo. Vuelve a intentar.')
                        contenido.extend(trozo)
                        if len(contenido) > maximo:
                            raise ErrorIA('La fuente curricular supera el tamaño permitido.')
                    return bytes(contenido), url
    except (httpx.HTTPError, OSError):
        raise ErrorIA('No fue posible descargar la fuente oficial. Se conserva la versión anterior.') from None
    raise ErrorIA('La fuente tiene demasiadas redirecciones.')


class _Enlaces(HTMLParser):
    def __init__(self):
        super().__init__(); self.urls = []

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            self.urls.extend(v for k, v in attrs if k == 'href' and v)


def localizar_pdf(fuente):
    """Descubre la descarga en la ficha aprobada; conserva el ID documental."""
    url_autorizada(fuente.descarga_url)
    try:
        html, ficha = descargar(fuente.ficha_url, maximo=2*1024*1024, plazo=time.monotonic()+18)
        parser = _Enlaces(); parser.feed(html.decode('utf-8', errors='replace'))
        identificador = re.search(r'articles-(\d+)', fuente.descarga_url)
        for enlace in parser.urls:
            url = urljoin(ficha, enlace)
            if identificador and re.search(r'articles-' + identificador[1] + r'[^/]*\.pdf(?:\?|$)', url):
                return url_autorizada(url)
    except ErrorIA:
        pass
    return fuente.descarga_url


def ruta_original(sha):
    if not re.fullmatch('[0-9a-f]{64}', sha):
        raise ErrorIA('Identificador de documento inválido.')
    return Path(settings.BIBLIOTECA_RAIZ) / (sha + '.pdf')


def guardar_original(sha, datos):
    ruta = ruta_original(sha)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    temporal = ruta.with_suffix('.' + uuid.uuid4().hex + '.tmp')
    try:
        temporal.write_bytes(datos)
        os.replace(temporal, ruta)
    finally:
        temporal.unlink(missing_ok=True)


def extraer(datos):
    if len(datos) > MAX_PDF or not datos.startswith(b'%PDF-'):
        raise ErrorIA('La fuente no es un PDF válido o supera el tamaño permitido.')
    try:
        lector = PdfReader(io.BytesIO(datos))
        if lector.is_encrypted or not 1 <= len(lector.pages) <= 400:
            raise ErrorIA('El PDF está protegido o excede 400 páginas.')
        from colegio.management.commands.indexar_documento_curricular import _fragmentar
        fragmentos, caracteres = [], 0
        inicio = time.monotonic()
        for n, pagina in enumerate(lector.pages, 1):
            texto = pagina.extract_text() or ''
            caracteres += len(texto)
            if caracteres > 3_000_000 or time.monotonic()-inicio > 90:
                raise ErrorIA('El PDF supera el límite de procesamiento curricular.')
            for trozo in _fragmentar(texto):
                fragmentos.append({'numero': len(fragmentos)+1, 'pagina': n, 'texto': trozo})
            if len(fragmentos) > MAX_FRAGMENTOS:
                raise ErrorIA('El documento contiene demasiados fragmentos.')
        if caracteres < 200 or not fragmentos:
            raise ErrorIA('El PDF no tiene texto suficiente. Requiere revisión u OCR antes de indexarlo.')
        return fragmentos
    except ErrorIA:
        raise
    except Exception:
        raise ErrorIA('No fue posible extraer texto del PDF. Se conserva la versión anterior.') from None


def sincronizar(fuente_id, informar=lambda m: None):
    """Arrendamiento con vencimiento: impide actualizaciones simultáneas."""
    ahora, token = timezone.now(), uuid.uuid4()
    adquirido = FuenteBiblioteca.objects.filter(pk=fuente_id, aprobada=True).filter(
        Q(bloqueo_hasta__isnull=True) | Q(bloqueo_hasta__lt=ahora)).update(
            bloqueo=token, bloqueo_hasta=ahora+timedelta(minutes=5), estado='actualizando',
            mensaje='Consultando la fuente oficial.')
    if not adquirido:
        raise ErrorIA('La fuente no está aprobada o ya tiene una actualización en curso.')
    try:
        fuente = FuenteBiblioteca.objects.get(pk=fuente_id)
        informar('Localizando el PDF en el catálogo oficial.')
        url = localizar_pdf(fuente)
        datos, url = descargar(url)
        sha = huella(datos)
        anterior = fuente.documentos.filter(sha256=sha).first()
        if anterior and anterior.fragmentos.exists():
            guardar_original(sha, datos)
            resumen = 'Sin cambios: se conservan los fragmentos y vectores existentes.'
            cantidad = anterior.fragmentos.count()
        else:
            informar('Extrayendo páginas e indexando texto localmente, sin API keys.')
            fragmentos = extraer(datos)
            guardar_original(sha, datos)
            with transaction.atomic():
                actual = FuenteBiblioteca.objects.select_for_update().get(pk=fuente_id)
                if actual.bloqueo != token or actual.bloqueo_hasta < timezone.now():
                    raise ErrorIA('La actualización caducó. Vuelve a intentar.')
                documento, nuevo = DocumentoCurricular.objects.get_or_create(sha256=sha, defaults={
                    'titulo': fuente.titulo, 'fuente_url': url, 'asignatura': fuente.asignatura,
                    'ciclo': fuente.ciclo, 'nivel': fuente.nivel, 'version': fuente.version,
                    'fuente_biblioteca': fuente})
                if not nuevo and (documento.fuente_biblioteca_id != fuente.pk or
                                  (documento.asignatura, documento.ciclo, documento.nivel) !=
                                  (fuente.asignatura, fuente.ciclo, fuente.nivel)):
                    raise ErrorIA('El PDF ya existe con otra clasificación. Requiere revisión del operador.')
                if not documento.fragmentos.exists():
                    FragmentoCurricular.objects.bulk_create([FragmentoCurricular(documento=documento, **f)
                        for f in fragmentos], batch_size=100)
                fuente.documentos.exclude(pk=documento.pk).update(activo=False)
                DocumentoCurricular.objects.filter(pk=documento.pk).update(activo=True)
            cantidad = len(fragmentos)
            resumen = f'Biblioteca disponible: {cantidad} fragmentos con páginas y fuente. Búsqueda textual local.'
        with transaction.atomic():
            actual = FuenteBiblioteca.objects.select_for_update().get(pk=fuente_id)
            if actual.bloqueo != token or actual.bloqueo_hasta < timezone.now():
                raise ErrorIA('La actualización caducó. Vuelve a intentar.')
            fuente.documentos.exclude(sha256=sha).update(activo=False)
            fuente.documentos.filter(sha256=sha).update(activo=True)
        FuenteBiblioteca.objects.filter(pk=fuente_id, bloqueo=token).update(estado='disponible',
            mensaje=resumen, comprobada=timezone.now(), proxima_revision=timezone.now()+timedelta(days=7))
        return {'fuente': fuente.slug, 'fragmentos': cantidad, 'sin_cambios': bool(anterior), 'mensaje': resumen}
    except Exception as e:
        FuenteBiblioteca.objects.filter(pk=fuente_id, bloqueo=token).update(estado='error',
            mensaje=str(e)[:400] if isinstance(e, ErrorIA) else 'Error al actualizar. Se conserva la versión anterior.',
            proxima_revision=timezone.now()+timedelta(hours=6))
        raise
    finally:
        FuenteBiblioteca.objects.filter(pk=fuente_id, bloqueo=token).update(bloqueo=None, bloqueo_hasta=None)


def limpiar_interrumpidas():
    ahora = timezone.now()
    FuenteBiblioteca.objects.filter(estado='actualizando', bloqueo_hasta__lt=ahora).update(
        estado='error', mensaje='La actualización fue interrumpida. Se conserva la versión anterior; puedes reintentar.',
        bloqueo=None, bloqueo_hasta=None, proxima_revision=ahora+timedelta(hours=6))
    base = Path(settings.BIBLIOTECA_RAIZ)
    if base.exists():
        for archivo in base.glob('*.tmp'):
            if archivo.is_file() and not archivo.is_symlink() and ahora.timestamp()-archivo.stat().st_mtime>86400:
                archivo.unlink(missing_ok=True)


def fragmentos_scope(*, asignatura, ciclo, nivel):
    return FragmentoCurricular.objects.filter(documento__activo=True,
        documento__fuente_biblioteca__aprobada=True, documento__asignatura__iexact=asignatura,
        documento__ciclo=ciclo, documento__nivel=nivel).select_related('documento', 'documento__fuente_biblioteca')


def _tokens(texto):
    t = unicodedata.normalize('NFKD', texto.lower())
    t = ''.join(c for c in t if not unicodedata.combining(c))
    tokens = re.findall(r'[a-z0-9]+', t)
    # Normaliza plurales de los dos contenidos del piloto sin confundir operaciones.
    cambios = {'multiplicaciones': 'multiplicacion', 'divisiones': 'division',
               'multiplicar': 'multiplicacion', 'dividir': 'division'}
    return [cambios.get(x, x) for x in tokens if len(x)>1 and x not in VACIAS]


def filas_buscables(base):
    """Las tablas de progresión mezclan columnas de cursos al extraer PDF.

    Se conservan indexadas, pero ninguna parte de esa página se usa como
    evidencia del curso: el encabezado puede estar en otro fragmento.
    """
    filas = list(base[:MAX_FRAGMENTOS+1])
    if len(filas)>MAX_FRAGMENTOS:
        raise ErrorIA('La biblioteca supera el límite de fragmentos por curso. El administrador debe revisar el catálogo.')
    niveles = {}
    for f in filas:
        clave = (f.documento_id, f.pagina)
        niveles.setdefault(clave,set()).update(re.findall(
            r'NIVEL\s+([1-8])\D{0,8}?(B[ÁA]SICO|MEDIO)', f.texto.upper()))
    return [f for f in filas if len(niveles[(f.documento_id, f.pagina)])<2 and
        all(int(grado)==f.documento.nivel and (ciclo.startswith('B') == (f.documento.ciclo=='BASICA'))
            for grado,ciclo in niveles[(f.documento_id,f.pagina)])]


def buscar_texto(*, consulta, asignatura, ciclo, nivel, limite=5):
    filas = filas_buscables(fragmentos_scope(asignatura=asignatura, ciclo=ciclo, nivel=nivel))
    consulta = set(_tokens(consulta))
    if not filas or not consulta:
        return []
    corpus = [Counter(_tokens(f.texto)) for f in filas]
    media = max(1, sum(sum(c.values()) for c in corpus)/len(corpus))
    df = Counter(t for c in corpus for t in consulta if t in c)
    resultados = []
    for f, c in zip(filas, corpus):
        score = sum(math.log(1+(len(corpus)-df[t]+.5)/(df[t]+.5)) * c[t]*2.5 /
                    (c[t]+1.5*(.25+.75*sum(c.values())/media)) for t in consulta if c[t])
        if score:
            resultados.append({'id': f'biblioteca-{f.documento.sha256[:12]}-{f.numero}', 'texto': f.texto,
                'pagina': f.pagina, 'titulo': f.documento.titulo, 'url': f.documento.fuente_url,
                'ficha_url': f.documento.fuente_biblioteca.ficha_url, 'version': f.documento.version,
                'sha256': f.documento.sha256, 'puntaje_bm25': score, 'similitud': None,
                'metodo_recuperacion': 'textual_biblioteca'})
    return sorted(resultados, key=lambda f: (-f['puntaje_bm25'], f['id']))[:max(0, min(limite, 10))]


def recuperar(**consulta):
    """Método explícito de la biblioteca; no requiere ni mezcla embeddings."""
    scope = {k: consulta[k] for k in ('asignatura', 'ciclo', 'nivel')}
    if fragmentos_scope(**scope).exists():
        if settings.BIBLIOTECA_BUSQUEDA == 'textual':
            return buscar_texto(**consulta)
        if settings.BIBLIOTECA_BUSQUEDA != 'vectorial':
            raise ErrorIA('El método de búsqueda de la biblioteca no es válido.')
        from .proveedor import proveedor_activo
        from .configuracion import valor
        from .rag import crear_embeddings
        from pgvector.django import CosineDistance
        proveedor = proveedor_activo()
        if proveedor not in ('gemini', 'qwen'):
            raise ErrorIA('La búsqueda vectorial necesita seleccionar un proveedor real.')
        campo = 'embedding_qwen' if proveedor == 'qwen' else 'embedding'
        base = fragmentos_scope(**scope)
        permitidos = [f.pk for f in filas_buscables(base)]
        if not permitidos:
            return []
        base = base.filter(pk__in=permitidos)
        if any(getattr(f, campo) is None or getattr(f, f'modelo_embedding_{proveedor}') != valor(proveedor, 'embedding_model')
               or getattr(f, f'huella_texto_{proveedor}') != huella(f.texto) for f in base):
            raise ErrorIA(f'La biblioteca tiene vectores {proveedor} pendientes para este curso. Completa su indexación o configura búsqueda textual.')
        vector = crear_embeddings([consulta['consulta']], tipo='RETRIEVAL_QUERY', proveedor=proveedor)[0]
        return [{'id': f'biblioteca-{f.documento.sha256[:12]}-{f.numero}', 'texto': f.texto,
            'titulo': f.documento.titulo, 'url': f.documento.fuente_url, 'pagina': f.pagina,
            'similitud': 1-float(f.distancia), 'distancia': float(f.distancia),
            'metodo_recuperacion': f'vectorial_{proveedor}'} for f in
            base.annotate(distancia=CosineDistance(campo, vector)).order_by('distancia')[:min(10, consulta.get('limite',5))]]
    # Corpus previo: conserva su contrato y validación del proveedor seleccionado.
    from . import rag
    return rag.buscar_fragmentos(**consulta)


def indexar_vectores(proveedor, *, maximo=50, informar=lambda m: None):
    """Operación explícita con cuota acotada y reanudable; jamás cambia proveedor."""
    if proveedor not in ('gemini', 'qwen') or not 1 <= maximo <= 200:
        raise ErrorIA('Selecciona Gemini o Qwen y un máximo de 1 a 200 fragmentos.')
    from .configuracion import valor
    from .rag import crear_embeddings
    campo = 'embedding' if proveedor == 'gemini' else 'embedding_qwen'
    modelo = str(valor(proveedor, 'embedding_model'))
    campos = [campo, f'modelo_embedding_{proveedor}', f'huella_texto_{proveedor}']
    pendientes = []
    for f in FragmentoCurricular.objects.filter(documento__activo=True, documento__fuente_biblioteca__aprobada=True).iterator():
        if getattr(f, campo) is None or getattr(f, campos[1]) != modelo or getattr(f, campos[2]) != huella(f.texto):
            pendientes.append(f)
            if len(pendientes) == maximo:
                break
    for inicio in range(0, len(pendientes), 8):
        lote = pendientes[inicio:inicio+8]
        vectores = crear_embeddings([f.texto for f in lote], tipo='RETRIEVAL_DOCUMENT', proveedor=proveedor)
        for f, vector in zip(lote, vectores):
            FragmentoCurricular.objects.filter(pk=f.pk, texto=f.texto).update(**dict(zip(campos,
                [vector, modelo, huella(f.texto)])))
        informar(f'{proveedor}: {min(inicio+8,len(pendientes))}/{len(pendientes)} fragmentos.')
    return len(pendientes)
