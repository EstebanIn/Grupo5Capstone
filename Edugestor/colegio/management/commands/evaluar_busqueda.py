"""Mide la búsqueda de la biblioteca con casos fijos y páginas esperadas.

La búsqueda textual no llama a la IA ni consume cuota. Uso:
    python manage.py evaluar_busqueda
    python manage.py evaluar_busqueda --sin-oa   # consulta solo con el tema, como antes del catálogo
"""
from django.core.management.base import BaseCommand

from colegio.ia import biblioteca, curriculo

# (nombre, OA oficial o None, tema, páginas del PDF que deberían aparecer entre las 5 primeras)
CASOS = [
    ('fracciones: equivalencia', 'MA04 OA 08', 'fracciones equivalentes', {102}),
    ('fracciones: comparar', 'MA04 OA 08', 'comparar y ordenar fracciones', {102}),
    ('fracciones: sumar', 'MA04 OA 09', 'suma de fracciones de igual denominador', {102}),
    ('números mixtos', 'MA04 OA 10', 'números mixtos en la recta numérica', {103}),
    ('multiplicación', 'MA04 OA 05', 'multiplicación de tres dígitos por un dígito', {58}),
    ('división', 'MA04 OA 06', 'división con divisor de un dígito', {58}),
    ('área', 'MA04 OA 23', 'área de rectángulos', {132}),
    ('decimales', 'MA04 OA 11', 'décimos y centésimos', {130}),
]
ALCANCE = {'asignatura': 'Matemática', 'ciclo': 'BASICA', 'nivel': 4}


class Command(BaseCommand):
    help = 'Mide qué páginas recupera la biblioteca para casos fijos (sin consumir cuota).'

    def add_arguments(self, parser):
        parser.add_argument('--sin-oa', action='store_true', help='Consulta solo con el tema, sin el texto del OA.')
        parser.add_argument('--limite', type=int, default=5)

    def handle(self, *args, sin_oa=False, limite=5, **options):
        aciertos = generales = 0
        for nombre, codigo, tema, esperadas in CASOS:
            oa = curriculo.objetivo(codigo)
            objetivo = '' if sin_oa or not oa else curriculo.texto_objetivo(oa)
            consulta = '\n'.join(x for x in (objetivo, tema) if x)
            resultados = biblioteca.buscar_texto(consulta=consulta, limite=limite, **ALCANCE)
            paginas = [r['pagina'] for r in resultados]
            acierto = bool(esperadas & set(paginas))
            ajenas = sum(biblioteca.es_general(r['texto']) for r in resultados)
            aciertos += acierto
            generales += ajenas
            self.stdout.write(f"{'OK ' if acierto else 'NO '} {nombre:28} esperadas {sorted(esperadas)} -> {paginas}")
        self.stdout.write(self.style.SUCCESS(
            f'Páginas esperadas encontradas: {aciertos}/{len(CASOS)}. Páginas generales entre los resultados: {generales}.'))
        if not sin_oa:
            self.stdout.write('Con OA elegido, su texto e indicadores además se entregan directamente a la IA.')
