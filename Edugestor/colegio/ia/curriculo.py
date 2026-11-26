"""Catálogo versionado de Objetivos de Aprendizaje oficiales (knowledge/oa/*.json).

El texto y los indicadores de cada OA se transcribieron del Programa de Estudio y
se revisaron contra el PDF. Cuando el docente elige un OA, ese texto llega siempre
a la IA, sin depender de que la búsqueda en la biblioteca lo encuentre.
"""
import json
import unicodedata
from functools import lru_cache
from pathlib import Path

from django.conf import settings

METODO = 'catalogo_oa'
REGLA_OFICIAL = ('Hay un OA oficial (texto e indicadores entregados como primer extracto): cada pregunta o '
                 'actividad debe evaluar ese OA y sus indicadores. No agregues contenidos de otros OA ni de otros niveles.')


def _clave(texto):
    texto = unicodedata.normalize('NFKD', str(texto or '').strip().lower())
    return ''.join(c for c in texto if not unicodedata.combining(c))


@lru_cache(maxsize=1)
def _catalogos():
    carpeta = Path(settings.BASE_DIR) / 'knowledge' / 'oa'
    catalogos = {}
    for ruta in sorted(carpeta.glob('*.json')):
        datos = json.loads(ruta.read_text(encoding='utf-8'))
        clave = (_clave(datos['asignatura']), datos['ciclo'], int(datos['nivel']))
        catalogos[clave] = datos
    return catalogos


def catalogo(asignatura, ciclo, nivel):
    """Catálogo del curso, o None si todavía no hay OA oficiales cargados."""
    try:
        return _catalogos().get((_clave(asignatura), ciclo, int(nivel)))
    except (TypeError, ValueError):
        return None


def catalogo_de_carga(carga):
    return catalogo(carga.asignatura.nombre_asignatura, carga.curso.ciclo, carga.curso.nivel)


def objetivo(codigo, *, carga=None):
    """El OA con ese código; si se indica la carga, solo si pertenece a su curso."""
    fuentes = [catalogo_de_carga(carga)] if carga is not None else _catalogos().values()
    for datos in fuentes:
        for oa in (datos or {}).get('objetivos', []):
            if oa['codigo'] == codigo:
                return {**oa, 'fuente': datos['fuente']}
    return None


def texto_objetivo(oa, foco=''):
    """Lo que se guarda como objetivo del documento: código, texto oficial y foco opcional."""
    texto = f"{oa['codigo']}: {oa['texto']}"
    foco = str(foco or '').strip()
    return f'{texto} Foco del docente: {foco}' if foco else texto


def fragmento(oa):
    """El OA y sus indicadores como primera fuente de la IA, con su página en el PDF."""
    lineas = [f"{oa['codigo']} (texto oficial): {oa['texto']}", 'Indicadores de evaluación sugeridos:']
    lineas += [f'- {indicador}' for indicador in oa['indicadores']]
    if oa.get('nota'):
        lineas.append(f"Nota de revisión: {oa['nota']}")
    return {'id': f"oa-{oa['codigo']}", 'texto': '\n'.join(lineas),
            'titulo': f"{oa['fuente']['titulo']} · {oa['codigo']}", 'url': oa['fuente']['url'],
            'pagina': oa['pagina_indicadores'], 'metodo_recuperacion': METODO, 'similitud': None}


def paginas_lista(carga):
    """Páginas del PDF con la lista completa de OA del curso."""
    datos = catalogo_de_carga(carga) or {}
    return {oa['pagina_lista'] for oa in datos.get('objetivos', [])}


def es_oficial(fragmentos):
    return any(f.get('metodo_recuperacion') == METODO for f in fragmentos or [])
