"""Proyección por destinatario antes de renderizar y PDF sin acceso a la red."""
from copy import deepcopy
from pathlib import Path
from urllib.parse import unquote, urlparse

from django.template.loader import render_to_string

from .proveedor import ErrorIA


def contenido_version(instrumento, version):
    if version not in ('estudiante', 'docente'):
        raise ErrorIA('Versión no válida.')
    original = instrumento.contenido
    base = {'titulo': original.get('titulo', instrumento.titulo), 'fuentes': original.get('fuentes', []),
            'instrucciones': original.get('instrucciones', 'Lee con atención y desarrolla las actividades.')}
    if instrumento.tipo == 'PRUEBA':
        base['preguntas'] = []
        for pregunta in original['preguntas']:
            item = {'enunciado': pregunta['enunciado'], 'alternativas': list(pregunta['alternativas'])}
            if version == 'docente':
                item.update(correcta=pregunta['correcta'], explicacion=pregunta.get('explicacion', ''))
            base['preguntas'].append(item)
    elif instrumento.tipo == 'RUBRICA':
        from .asistentes import validar_rubrica
        base.update(validar_rubrica(original))
    else:
        separado = original.get('version_estructura') == 2
        if version == 'estudiante' and (not separado or not original.get('separacion_revisada')):
            raise ErrorIA('Este material requiere una copia editable y revisión de la separación de respuestas antes de exportarlo para estudiantes.')
        if separado:
            base.update(contenido=original.get('contenido', ''), ejercicios=original.get('ejercicios', ''))
            if version == 'docente':
                base['solucionario'] = original.get('solucionario', '')
        elif version == 'docente':
            base['contenido'] = original.get('texto', '')
    return base


def contexto_documento(instrumento, version):
    return {'documento': contenido_version(instrumento, version), 'instrumento': instrumento,
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
    return HTML(string=html, url_fetcher=recurso_local).write_pdf()
