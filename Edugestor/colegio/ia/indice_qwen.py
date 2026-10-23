"""Cobertura y reindexación Qwen sin modificar los vectores Gemini."""
import hashlib
import json
import os
from pathlib import Path
from django.conf import settings
from django.db import transaction
from .proveedor import ErrorIA

def huella(texto):
    return hashlib.sha256(texto.encode('utf-8')).hexdigest()

def rutas_tutor():
    base = Path(settings.BASE_DIR)/'knowledge'/'procesados'/'libro_matematica_embeddings.json'
    return base, base.with_name('libro_matematica_embeddings.qwen.json')

def corpus_tutor():
    base, _ = rutas_tutor()
    try:
        contenido = base.read_bytes()
        documentos = json.loads(contenido)
        if not isinstance(documentos, list) or not documentos or any(not isinstance(d.get('texto'), str) or not d['texto'].strip() for d in documentos):
            raise ValueError
        return documentos, hashlib.sha256(contenido).hexdigest()
    except (OSError, ValueError, TypeError, AttributeError):
        raise ErrorIA('El corpus del tutor no está disponible o no es válido.') from None

def cargar_indice():
    _, ruta = rutas_tutor()
    try:
        indice = json.loads(ruta.read_text(encoding='utf-8'))
        if indice.get('modelo') != settings.QWEN_EMBEDDING_MODEL or indice.get('dimensiones') != 768:
            return {}
        return indice
    except (OSError, ValueError, AttributeError):
        return {}

def vector_valido(vector):
    import math
    return isinstance(vector, list) and len(vector) == 768 and all(isinstance(v, (float, int)) and math.isfinite(v) for v in vector) and any(vector)

def estado_indices():
    from colegio.models import FragmentoCurricular
    filas = FragmentoCurricular.objects.filter(documento__activo=True).values('texto','embedding_qwen','modelo_embedding_qwen','huella_texto_qwen')
    total = completos = 0
    for f in filas:
        total += 1
        if f['embedding_qwen'] is not None and f['modelo_embedding_qwen'] == settings.QWEN_EMBEDDING_MODEL and f['huella_texto_qwen'] == huella(f['texto']):
            completos += 1
    try:
        documentos, sha = corpus_tutor()
        indice = cargar_indice()
        vectores = indice.get('vectores', {})
        tutor_ok = sum(vector_valido(vectores.get(huella(d['texto']))) for d in documentos) if indice.get('base_sha256') == sha else 0
        tutor_total = len(documentos)
    except ErrorIA:
        tutor_ok = tutor_total = 0
    return {'curricular_total': total, 'curricular_completos': completos, 'tutor_total': tutor_total, 'tutor_completos': tutor_ok,
            'completo': total > 0 and completos == total and tutor_total > 0 and tutor_ok == tutor_total}

def exigir_indice_completo():
    if not estado_indices()['completo']:
        raise ErrorIA('El índice RAG de Qwen está incompleto. Solicita al administrador completar la indexación. No se cambió a Gemini.')

def documentos_tutor_qwen():
    exigir_indice_completo()
    documentos, _ = corpus_tutor()
    vectores = cargar_indice()['vectores']
    return [{**d, 'embedding': vectores[huella(d['texto'])]} for d in documentos]

def reindexar_qwen(informar=lambda texto: None):
    from colegio.models import FragmentoCurricular
    from .qwen import embeddings
    pendientes = []
    for f in FragmentoCurricular.objects.filter(documento__activo=True).iterator(chunk_size=100):
        if f.embedding_qwen is None or f.modelo_embedding_qwen != settings.QWEN_EMBEDDING_MODEL or f.huella_texto_qwen != huella(f.texto):
            pendientes.append(f)
    for inicio in range(0, len(pendientes), 10):
        lote = pendientes[inicio:inicio+10]
        vectores = embeddings([f.texto for f in lote], tipo='RETRIEVAL_DOCUMENT')
        with transaction.atomic():
            for f, vector in zip(lote, vectores):
                FragmentoCurricular.objects.filter(pk=f.pk, texto=f.texto).update(embedding_qwen=vector,modelo_embedding_qwen=settings.QWEN_EMBEDDING_MODEL,huella_texto_qwen=huella(f.texto))
        informar('Curricular Qwen: %s/%s fragmentos pendientes procesados.' % (min(inicio+10,len(pendientes)),len(pendientes)))
    documentos, sha = corpus_tutor()
    indice = cargar_indice()
    vectores = indice.get('vectores', {})
    textos = list(dict.fromkeys(d['texto'] for d in documentos if not vector_valido(vectores.get(huella(d['texto'])))))
    _, ruta = rutas_tutor()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    def guardar():
        temporal = ruta.with_suffix('.tmp')
        temporal.write_text(json.dumps({'proveedor':'qwen','modelo':settings.QWEN_EMBEDDING_MODEL,'dimensiones':768,'base_sha256':sha,'vectores':vectores}), encoding='utf-8')
        os.replace(temporal,ruta)
    for inicio in range(0,len(textos),10):
        lote=textos[inicio:inicio+10]
        nuevos=embeddings(lote,tipo='RETRIEVAL_DOCUMENT')
        vectores.update((huella(t),v) for t,v in zip(lote,nuevos))
        guardar()
        informar('Tutor Qwen: %s/%s textos pendientes procesados.' % (min(inicio+10,len(textos)),len(textos)))
    guardar()
    return estado_indices()
