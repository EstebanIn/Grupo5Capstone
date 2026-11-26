"""Controles del servidor sobre la prueba generada, a partir de errores observados con Qwen."""
import random
from collections import Counter
from unittest import mock

from django.test import SimpleTestCase

from .ia import asistentes
from .ia.ejecucion import usar_proveedor

INDICACION = asistentes.instruccion_desarrollo('Matemática')
# Texto entregado por qwen4-max en la prueba de fracciones de 4° básico.
INSTRUCCIONES_REALES = (
    'Lee con calma cada pregunta antes de responder. En las preguntas de desarrollo debes mostrar '
    'cómo llegaste a la respuesta: escribe tus pasos en el recuadro de desarrollo, la operación o '
    'propiedad que usaste en el recuadro de fórmula y tu respuesta final en el recuadro de resultado. '
    'Puedes hacer dibujos de tiras, círculos o rectas numéricas para ayudarte.')


def seleccion(enunciado, alternativas, correcta):
    return {'tipo': 'seleccion', 'enunciado': enunciado, 'alternativas': list(alternativas),
            'correcta': correcta, 'explicacion': 'Porque sí.'}


class InstruccionesTests(SimpleTestCase):
    def test_indicacion_de_recuadros_aparece_una_sola_vez(self):
        texto = asistentes.instrucciones_prueba(INSTRUCCIONES_REALES, INDICACION)
        self.assertEqual(texto.count('recuadro'), INDICACION.count('recuadro'))
        self.assertTrue(texto.endswith(INDICACION))
        self.assertIn('Puedes hacer dibujos de tiras', texto)

    def test_sin_desarrollo_no_cambia_las_instrucciones(self):
        self.assertEqual(asistentes.instrucciones_prueba('Marca una alternativa.', ''), 'Marca una alternativa.')


class OrdenAlternativasTests(SimpleTestCase):
    def test_conserva_la_correcta_y_reparte_las_posiciones(self):
        # Ocho preguntas con el patrón observado C-A-D-B-C-A-D-B.
        preguntas = [seleccion(f'P{i}', [f'opcion{i}a', f'opcion{i}b', f'opcion{i}c', f'opcion{i}d'], 'ABCD'.index(letra))
                     for i, letra in enumerate('CADBCADB')]
        correctas = [p['alternativas'][p['correcta']] for p in preguntas]
        asistentes.ordenar_alternativas(preguntas, random.Random(3))
        self.assertEqual([p['alternativas'][p['correcta']] for p in preguntas], correctas)
        self.assertEqual(Counter(p['correcta'] for p in preguntas), Counter({0: 2, 1: 2, 2: 2, 3: 2}))
        for p in preguntas:
            self.assertEqual(len(set(p['alternativas'])), 4)

    def test_alternativas_numericas_quedan_de_menor_a_mayor(self):
        p = seleccion('1/2 = ?/8', ['6', '2', '4', '3'], 2)
        f = seleccion('Mayor que 1/2', ['3/8', '5/8', '4/10', '2/6'], 1)
        asistentes.ordenar_alternativas([p, f], random.Random(0))
        self.assertEqual(p['alternativas'], ['2', '3', '4', '6'])
        self.assertEqual(p['alternativas'][p['correcta']], '4')
        self.assertEqual(f['alternativas'], ['2/6', '3/8', '4/10', '5/8'])
        self.assertEqual(f['alternativas'][f['correcta']], '5/8')

    def test_no_toca_las_preguntas_de_desarrollo(self):
        desarrollo = {'tipo': 'desarrollo', 'enunciado': 'Explica', 'criterios': []}
        asistentes.ordenar_alternativas([desarrollo], random.Random(0))
        self.assertEqual(desarrollo, {'tipo': 'desarrollo', 'enunciado': 'Explica', 'criterios': []})


class CrearPruebaTests(SimpleTestCase):
    contexto = {'curso': '4° Básico A', 'nivel': '4° básico', 'asignatura': 'Matemática'}

    def generar(self, proveedor):
        respuesta = {'titulo': 'Prueba', 'instrucciones': INSTRUCCIONES_REALES, 'preguntas': [
            seleccion(f'Pregunta {i}', [f'x{i}', f'y{i}', f'z{i}', f'w{i}'], i % 4) for i in range(4)] + [
            {'tipo': 'desarrollo', 'enunciado': 'Explica', 'criterios': asistentes.componentes_desarrollo('Matemática')}]}
        with usar_proveedor(proveedor), mock.patch.object(asistentes, 'generar', return_value=respuesta):
            return asistentes.crear_prueba(self.contexto, '', 'fracciones', 4, 'media', cantidad_desarrollo=1)

    def test_con_proveedor_real_corrige_instrucciones_y_conserva_las_claves(self):
        resultado = self.generar('qwen')
        self.assertEqual(resultado['instrucciones'].count(INDICACION), 1)
        self.assertNotIn('recuadro de fórmula', resultado['instrucciones'])
        for i, p in enumerate(resultado['preguntas'][:4]):
            self.assertEqual(p['alternativas'][p['correcta']], ['x', 'y', 'z', 'w'][i % 4] + str(i))

    def test_modo_simulado_conserva_el_orden_del_ejemplo(self):
        resultado = self.generar('simulado')
        self.assertEqual([p['correcta'] for p in resultado['preguntas'][:4]], [0, 1, 2, 3])
