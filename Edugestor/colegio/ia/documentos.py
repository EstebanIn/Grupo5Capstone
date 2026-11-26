"""Proyección por destinatario antes de renderizar y PDF sin acceso a la red."""
from copy import deepcopy
from pathlib import Path
from urllib.parse import unquote, urlparse

from django.template.loader import render_to_string

from .proveedor import ErrorIA


INSTRUCCIONES = {
    ('RUBRICA', 'estudiante'): 'Esta rúbrica muestra cómo se evaluará tu trabajo. Léela antes de comenzar.',
    ('RUBRICA', 'docente'): 'Marca el nivel observado en cada criterio y anota su puntaje. Sin evidencia: 0 puntos.',
    ('MATERIAL', 'estudiante'): 'Lee la explicación y luego resuelve los ejercicios.',
    ('MATERIAL', 'docente'): 'Versión con solucionario para el docente.',
}


def contenido_version(instrumento, version):
    if version not in ('estudiante', 'docente'):
        raise ErrorIA('Versión no válida.')
    original = instrumento.contenido
    instrucciones = original.get('instrucciones') or INSTRUCCIONES.get(
        (instrumento.tipo, version), 'Lee con atención y desarrolla las actividades.')
    # Las fuentes recuperadas orientan al docente; no son parte de lo que lee el estudiante.
    base = {'titulo': original.get('titulo', instrumento.titulo),
            'fuentes': original.get('fuentes', []) if version == 'docente' else [],
            'instrucciones': instrucciones}
    if instrumento.tipo == 'PRUEBA':
        from .asistentes import es_asignatura_de_calculo, es_desarrollo, puntaje_pregunta, puntaje_total_prueba
        base['preguntas'] = []
        for pregunta in original['preguntas']:
            if es_desarrollo(pregunta):
                # El estudiante ve los recuadros con su nombre y puntaje; la pauta queda solo para el docente.
                item = {'tipo': 'desarrollo', 'enunciado': pregunta['enunciado'],
                        'puntaje': puntaje_pregunta(pregunta),
                        'criterios': [{'clave': c['clave'], 'nombre': c['nombre'], 'puntaje_maximo': c['puntaje_maximo']}
                                      for c in pregunta.get('criterios', [])]}
                if version == 'docente':
                    item.update(formula=pregunta.get('formula', ''), resultado=pregunta.get('resultado', ''),
                                desarrollo_esperado=pregunta.get('desarrollo_esperado', ''),
                                explicacion=pregunta.get('explicacion', ''),
                                criterios=deepcopy(pregunta.get('criterios', [])))
                base['preguntas'].append(item)
                continue
            item = {'tipo': 'seleccion', 'enunciado': pregunta['enunciado'], 'alternativas': list(pregunta['alternativas'])}
            if version == 'docente':
                item.update(correcta=pregunta['correcta'], explicacion=pregunta.get('explicacion', ''))
            base['preguntas'].append(item)
        base['puntaje_total'] = puntaje_total_prueba(original)
        base['hay_desarrollo'] = any(es_desarrollo(p) for p in original['preguntas'])
        base['cuadricula'] = es_asignatura_de_calculo(instrumento.carga.asignatura.nombre_asignatura)
    elif instrumento.tipo == 'RUBRICA':
        from .asistentes import validar_rubrica
        base.update(validar_rubrica(original))
    else:
        separado = original.get('version_estructura') == 2
        if version == 'estudiante' and (not separado or not original.get('separacion_revisada')):
            raise ErrorIA('Este material requiere una copia editable y revisión de la separación de respuestas antes de exportarlo para estudiantes.')
        if separado:
            base.update(contenido=original.get('contenido', ''), ejercicios=original.get('ejercicios', ''))
            from .visuales import validar_visuales
            recursos = validar_visuales(original.get('recursos_visuales', []))
            base['recursos_visuales'] = [r for r in recursos if version == 'docente' or r['ubicacion'] != 'solucionario']
            if version == 'docente':
                base['solucionario'] = original.get('solucionario', '')
        elif version == 'docente':
            base['contenido'] = original.get('texto', '')
        if original.get('ficha'):
            # La ficha no lleva respuestas: va en ambas versiones, revalidada antes de dibujarla.
            from .ficha import validar_ficha
            base['ficha'] = validar_ficha(original['ficha'])
    return base


def contexto_documento(instrumento, version):
    documento=contenido_version(instrumento, version)
    referencias={}
    for f in documento.get('fuentes',[]):
        clave=(f.get('titulo',''),f.get('url',''))
        r=referencias.setdefault(clave,{'titulo':clave[0],'url':clave[1],'paginas':[]})
        if f.get('pagina') is not None and f['pagina'] not in r['paginas']:r['paginas'].append(f['pagina'])
    for r in referencias.values():r['paginas'].sort(key=lambda p:int(p) if str(p).isdigit() else 10**9)
    return {'documento': documento, 'instrumento': instrumento, 'referencias':list(referencias.values()),
            'institucion': instrumento.institucion, 'version': version,
            'horizontal': instrumento.tipo == 'RUBRICA'}


def recurso_local(url, timeout=10, ssl_context=None):
    """Allowlist de recursos empaquetados. Bloquea HTTP, data y archivos privados."""
    from weasyprint import default_url_fetcher
    partes = urlparse(url)
    base = (Path(__file__).resolve().parents[1] / 'static' / 'documentos').resolve()
    ruta = Path(unquote(partes.path)).resolve()
    if (partes.scheme != 'file' or partes.netloc or not ruta.is_relative_to(base)
            or ruta.suffix.lower() not in ('.png', '.jpg', '.jpeg', '.woff2') or ruta.is_symlink()):
        raise ValueError('Recurso PDF no autorizado')
    return default_url_fetcher(url, timeout=timeout, ssl_context=ssl_context)


def generar_pdf(instrumento, version):
    from weasyprint import HTML
    html = render_to_string('colegio/ia/documento.html', contexto_documento(instrumento, version))
    return HTML(string=html, url_fetcher=recurso_local).write_pdf(presentational_hints=True)
