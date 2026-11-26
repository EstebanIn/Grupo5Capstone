"""Aplicar a una copia las mejoras de una revisión de calidad y elegir cambio por cambio."""
from django.test import SimpleTestCase
from django.urls import reverse

from .ia import asistentes
from .models import InstrumentoIA, TrabajoIA
from .tests import AsistenteIATestBase

REVISION = """## Resumen

La prueba está bien construida en lo esencial.

## Observaciones por pregunta

### Pregunta 1 — falta la figura

Propuesta: insertar el rectángulo dibujado.

### Pregunta 3 — pista involuntaria por extensión

A) Comieron lo mismo. D) 5/8 es mayor. Clave: D.

## Observaciones generales

**Instrucciones:** están duplicadas. Versión corta: lee con calma.

## Fortalezas

- Las claves son correctas.
"""


class SeccionesRevisionTests(SimpleTestCase):
    def test_separa_preguntas_y_generales_sin_resumen_ni_fortalezas(self):
        secciones = asistentes.secciones_revision(REVISION)

        self.assertEqual([s['clave'] for s in secciones], ['p1', 'p3', 'g1'])
        self.assertEqual(secciones[0]['pregunta'], 1)
        self.assertIn('rectángulo', secciones[0]['texto'])
        self.assertEqual(secciones[2]['titulo'], 'Observaciones generales')
        self.assertNotIn('claves son correctas', ' '.join(s['texto'] for s in secciones))

    def test_reconoce_vinetas_y_agrupa_la_misma_pregunta(self):
        texto = "### Observaciones\n\n- **Pregunta 2:** cambia la clave.\n- **Pregunta 2:** acorta el enunciado.\n"
        secciones = asistentes.secciones_revision(texto)

        self.assertEqual([s['clave'] for s in secciones], ['p2'])
        self.assertIn('cambia la clave', secciones[0]['texto'])
        self.assertIn('acorta el enunciado', secciones[0]['texto'])


class AplicarMejorasTests(AsistenteIATestBase):
    def revisar(self, prueba=None):
        url = reverse('ia_revisar_prueba') + (f'?instrumento={prueba.pk}' if prueba else '')
        respuesta = self.client.post(url, {'carga': self.carga.pk, 'texto': '1. ¿Cuánto es 1/2 + 1/4?'})
        return TrabajoIA.objects.get(pk=respuesta.url.rstrip('/').split('/')[-1])

    def setUp(self):
        super().setUp()
        self.client.force_login(self.usuario_docente)
        self.crear_prueba(cantidad=3)
        self.original = InstrumentoIA.objects.get()

    def test_revision_desde_la_prueba_ofrece_aplicar_mejoras(self):
        revision = self.revisar(self.original)

        self.assertEqual(revision.instrumento_id, self.original.pk)
        pagina = self.client.get(reverse('ia_trabajo', args=[revision.pk]))
        self.assertContains(pagina, 'Aplicar mejoras a la prueba')
        self.assertContains(pagina, 'value="p1"')
        self.assertContains(pagina, 'value="g1"')

    def test_crea_una_copia_y_conserva_la_original(self):
        revision = self.revisar(self.original)
        antes = self.original.contenido

        self.client.post(reverse('ia_aplicar_mejoras', args=[revision.pk]), {'secciones': ['p1']})

        copia = InstrumentoIA.objects.exclude(pk=self.original.pk).get()
        self.original.refresh_from_db()
        self.assertEqual(self.original.contenido, antes)
        self.assertEqual(copia.parametros['mejora_de'], self.original.pk)
        self.assertEqual(copia.estado, InstrumentoIA.ESTADO_BORRADOR)
        self.assertNotEqual(copia.contenido['preguntas'][0], antes['preguntas'][0])
        self.assertEqual(copia.contenido['preguntas'][1:], antes['preguntas'][1:])
        self.assertEqual(copia.contenido['instrucciones'], antes['instrucciones'])
        trabajo = TrabajoIA.objects.get(operacion='mejora')
        self.assertEqual(trabajo.resultado['cambios'], [1])

    def test_el_docente_elige_original_o_mejora_por_pregunta(self):
        revision = self.revisar(self.original)
        # Una observación general puede tocar todas las preguntas y las instrucciones.
        self.client.post(reverse('ia_aplicar_mejoras', args=[revision.pk]), {'secciones': ['g1']})
        copia = InstrumentoIA.objects.exclude(pk=self.original.pk).get()
        url = reverse('ia_comparar_mejora', args=[copia.pk])

        pagina = self.client.get(url)
        self.assertContains(pagina, 'Pregunta 1')
        self.assertContains(pagina, 'name="instrucciones"')

        self.client.post(url, {'p1': 'original', 'p2': 'mejora', 'p3': 'mejora', 'instrucciones': 'mejora'})
        copia.refresh_from_db()
        self.assertEqual(copia.contenido['preguntas'][0], self.original.contenido['preguntas'][0])
        self.assertNotEqual(copia.contenido['preguntas'][1], self.original.contenido['preguntas'][1])
        self.assertNotEqual(copia.contenido['instrucciones'], self.original.contenido['instrucciones'])
        self.assertTrue(copia.parametros['mejora_revisada'])

        # La propuesta se conserva: se puede volver a elegir.
        self.client.post(url, {'p1': 'mejora', 'p2': 'original', 'p3': 'original', 'instrucciones': 'original'})
        copia.refresh_from_db()
        self.assertNotEqual(copia.contenido['preguntas'][0], self.original.contenido['preguntas'][0])
        self.assertEqual(copia.contenido['preguntas'][1], self.original.contenido['preguntas'][1])

    def test_revision_de_texto_pegado_no_aplica_mejoras(self):
        revision = self.revisar()

        pagina = self.client.get(reverse('ia_trabajo', args=[revision.pk]))
        self.assertContains(pagina, 'texto pegado')
        self.client.post(reverse('ia_aplicar_mejoras', args=[revision.pk]), {'secciones': ['p1']})
        self.assertFalse(TrabajoIA.objects.filter(operacion='mejora').exists())

    def test_sin_observaciones_elegidas_no_crea_trabajo(self):
        revision = self.revisar(self.original)

        self.client.post(reverse('ia_aplicar_mejoras', args=[revision.pk]), {'secciones': ['p99']})
        self.assertFalse(TrabajoIA.objects.filter(operacion='mejora').exists())

    def test_otro_docente_no_aplica_ni_compara(self):
        revision = self.revisar(self.original)
        self.client.post(reverse('ia_aplicar_mejoras', args=[revision.pk]), {'secciones': ['p1']})
        copia = InstrumentoIA.objects.exclude(pk=self.original.pk).get()
        self.client.force_login(self.usuario_otro_docente)

        self.assertEqual(self.client.post(reverse('ia_aplicar_mejoras', args=[revision.pk]),
                                          {'secciones': ['p1']}).status_code, 404)
        self.assertEqual(self.client.get(reverse('ia_comparar_mejora', args=[copia.pk])).status_code, 404)
