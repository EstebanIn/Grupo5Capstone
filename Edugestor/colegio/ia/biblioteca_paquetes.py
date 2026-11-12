"""Paquetes portables de fuentes públicas. No serializa modelos de usuario."""
import io
import json
import math
import zipfile
from pathlib import PurePosixPath

from django.db import transaction
from django.utils import timezone

from colegio.models import DocumentoCurricular, FragmentoCurricular, FuenteBiblioteca
from .biblioteca import extraer, guardar_original, huella, ruta_original, url_autorizada
from .configuracion import valor
from .proveedor import ErrorIA

FORMATO = 'edugestor-biblioteca-v1'
MAX_PAQUETE = 100*1024*1024


def exportar():
    buffer = io.BytesIO()
    documentos = list(DocumentoCurricular.objects.filter(activo=True,
        fuente_biblioteca__aprobada=True).select_related('fuente_biblioteca')[:17])
    if not documentos or len(documentos)>16:
        raise ErrorIA('Exporta entre uno y dieciséis documentos de la biblioteca pública.')
    indice = {'formato': FORMATO, 'creado': timezone.now().isoformat(), 'documentos': []}
    total = 0
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as z:
        for d in documentos:
            ruta = ruta_original(d.sha256)
            if not ruta.is_file():
                raise ErrorIA('Falta un original de la biblioteca. Actualiza su fuente antes de exportar.')
            pdf = ruta.read_bytes()
            if huella(pdf) != d.sha256:
                raise ErrorIA('El original no supera su comprobación de integridad. Actualiza la fuente.')
            vectores = []
            for f in d.fragmentos.all():
                v = {'numero': f.numero, 'texto_sha256': huella(f.texto)}
                for proveedor, campo in (('gemini', 'embedding'), ('qwen', 'embedding_qwen')):
                    vector = getattr(f, campo)
                    modelo = getattr(f, f'modelo_embedding_{proveedor}')
                    if vector is not None and modelo and getattr(f, f'huella_texto_{proveedor}') == huella(f.texto):
                        v[proveedor] = {'modelo': modelo, 'dimensiones': 768, 'vector': list(map(float, vector))}
                if len(v)>2:
                    vectores.append(v)
            datos_vectores = json.dumps(vectores, allow_nan=False).encode()
            total += len(pdf)+len(datos_vectores)
            if total>MAX_PAQUETE-1024*1024:
                raise ErrorIA('La biblioteca supera el tamaño máximo del paquete.')
            nombre, vect = f'originales/{d.sha256}.pdf', f'vectores/{d.sha256}.json'
            z.writestr(nombre, pdf); z.writestr(vect, datos_vectores)
            indice['documentos'].append({'fuente': d.fuente_biblioteca.slug, 'sha256': d.sha256,
                'pdf': nombre, 'vectores': vect, 'vectores_sha256': huella(datos_vectores),
                'titulo': d.titulo, 'url': d.fuente_url, 'asignatura': d.asignatura,
                'ciclo': d.ciclo, 'nivel': d.nivel, 'version': d.version,
                'ficha_url': d.fuente_biblioteca.ficha_url, 'licencia': d.fuente_biblioteca.licencia})
        z.writestr('manifiesto.json', json.dumps(indice, ensure_ascii=False))
    return buffer.getvalue()


def _vector(valor_vector):
    return (isinstance(valor_vector, list) and len(valor_vector)==768 and
        all(type(x) in (int, float) and math.isfinite(x) for x in valor_vector) and any(valor_vector))


def importar(datos):
    """El operador importa solo fuentes previamente aprobadas en este equipo.

    El hash detecta corrupción, no acredita la autoría del paquete: debe venir de
    una instalación de confianza. El texto se vuelve a extraer del PDF original.
    """
    if len(datos)>MAX_PAQUETE:
        raise ErrorIA('El paquete excede 100 MB.')
    try:
        with zipfile.ZipFile(io.BytesIO(datos)) as z:
            archivos = z.infolist()
            nombres = [a.filename for a in archivos]
            if len(archivos)>33 or len(set(nombres))!=len(nombres) or sum(a.file_size for a in archivos)>MAX_PAQUETE:
                raise ValueError
            for a in archivos:
                p = PurePosixPath(a.filename)
                if p.is_absolute() or '..' in p.parts or '\\' in a.filename or a.is_dir() or (a.external_attr>>16)&0o170000 == 0o120000:
                    raise ValueError
            if z.getinfo('manifiesto.json').file_size>1024*1024:
                raise ValueError
            indice = json.loads(z.read('manifiesto.json'))
            if indice['formato']!=FORMATO or not 1<=len(indice['documentos'])<=16:
                raise ValueError
            preparados, permitidos, fuentes = [], {'manifiesto.json'}, set()
            for d in indice['documentos']:
                fuente = FuenteBiblioteca.objects.get(slug=d['fuente'], aprobada=True)
                if fuente.pk in fuentes or (d['asignatura'], d['ciclo'], d['nivel']) != (fuente.asignatura, fuente.ciclo, fuente.nivel):
                    raise ValueError
                fuentes.add(fuente.pk)
                url_autorizada(d['url'])
                sha = d['sha256']; ruta_original(sha)
                if d['pdf']!=f'originales/{sha}.pdf' or d['vectores']!=f'vectores/{sha}.json':
                    raise ValueError
                pdf, vect = z.read(d['pdf']), z.read(d['vectores'])
                if huella(pdf)!=sha or huella(vect)!=d['vectores_sha256']:
                    raise ValueError
                fragmentos = extraer(pdf)
                vectores = json.loads(vect)
                if not isinstance(vectores, list) or len(vectores)>len(fragmentos):
                    raise ValueError
                por_numero = {f['numero']: f for f in fragmentos}
                vistos = set()
                for v in vectores:
                    f = por_numero[v['numero']]
                    if v['numero'] in vistos or v['texto_sha256']!=huella(f['texto']):
                        raise ValueError
                    vistos.add(v['numero'])
                    for proveedor, campo in (('gemini', 'embedding'), ('qwen', 'embedding_qwen')):
                        if proveedor not in v:
                            continue
                        item = v[proveedor]
                        if item['dimensiones']!=768 or not _vector(item['vector']):
                            raise ValueError
                        if item['modelo']==valor(proveedor, 'embedding_model'):
                            f.update({campo: item['vector'], f'modelo_embedding_{proveedor}': item['modelo'],
                                      f'huella_texto_{proveedor}': huella(f['texto'])})
                permitidos.update([d['pdf'],d['vectores']])
                preparados.append((fuente,d,pdf,fragmentos))
            if set(nombres)!=permitidos:
                raise ValueError
    except ErrorIA:
        raise
    except (ValueError, KeyError, TypeError, OSError, RuntimeError, IndexError, zipfile.BadZipFile, FuenteBiblioteca.DoesNotExist):
        raise ErrorIA('Paquete inválido, dañado o con fuentes no aprobadas en este equipo.') from None
    with transaction.atomic():
        for fuente, d, pdf, fragmentos in preparados:
            fuente = FuenteBiblioteca.objects.select_for_update().get(pk=fuente.pk, aprobada=True)
            if fuente.bloqueo_hasta and fuente.bloqueo_hasta>timezone.now():
                raise ErrorIA('Una fuente se está actualizando. Importa cuando termine.')
            documento, nuevo = DocumentoCurricular.objects.get_or_create(sha256=d['sha256'], defaults={
                'fuente_biblioteca': fuente, 'titulo': fuente.titulo, 'fuente_url': d['url'],
                'asignatura': fuente.asignatura, 'ciclo': fuente.ciclo, 'nivel': fuente.nivel,
                'version': str(d['version'])[:80]})
            if documento.fuente_biblioteca_id!=fuente.pk:
                raise ErrorIA('El documento ya existe con otra clasificación. Requiere revisión.')
            guardar_original(d['sha256'],pdf)
            if nuevo or not documento.fragmentos.exists():
                FragmentoCurricular.objects.bulk_create([FragmentoCurricular(documento=documento, **f) for f in fragmentos], batch_size=100)
            else:
                for f in fragmentos:
                    compatibles = {k: v for k,v in f.items() if k not in ('numero','pagina','texto')}
                    if compatibles:
                        FragmentoCurricular.objects.filter(documento=documento, numero=f['numero'],
                            texto=f['texto']).update(**compatibles)
            fuente.documentos.exclude(pk=documento.pk).update(activo=False)
            DocumentoCurricular.objects.filter(pk=documento.pk).update(activo=True)
            FuenteBiblioteca.objects.filter(pk=fuente.pk).update(estado='disponible',
                mensaje='Biblioteca importada; búsqueda textual disponible.', comprobada=timezone.now())
    return len(preparados)
