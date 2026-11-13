"""Fuentes revisadas. Ampliar este catálogo exige revisar nivel, origen y derechos."""
PILOTO = {
    'slug': 'mineduc-matematica-4-basico',
    'titulo': 'Programa de Estudio Matemática · 4° básico',
    'ficha_url': 'https://www.curriculumnacional.cl/recursos/programa-estudio-matematica-4-basico',
    'descarga_url': 'https://www.curriculumnacional.cl/614/articles-18979_programa.pdf',
    'asignatura': 'Matemática', 'ciclo': 'BASICA', 'nivel': 4,
    'licencia': 'MINEDUC. Consultar condiciones de reutilización en la ficha y el documento original.',
    'version': 'Programa de estudio (edición del PDF oficial)',
    'aprobada': True, 'automatica': True,
}


def preparar_catalogo():
    from colegio.models import FuenteBiblioteca
    # No reactiva fuentes que el operador haya deshabilitado.
    return FuenteBiblioteca.objects.get_or_create(slug=PILOTO['slug'], defaults=PILOTO)[0]
