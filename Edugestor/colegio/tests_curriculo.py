"""Catálogo de OA oficiales y fuentes de la IA (fase 2 del plan de mejora)."""

from django.test import SimpleTestCase
from django.urls import reverse

from .ia import biblioteca, curriculo
from .ia.formularios import FormularioPrueba
from .models import InstrumentoIA
from .tests import AsistenteIATestBase


class CatalogoTests(SimpleTestCase):
    def test_catalogo_de_matematica_4_completo(self):
        datos = curriculo.catalogo('Matemática', 'BASICA', 4)
        codigos = [oa['codigo'] for oa in datos['objetivos']]
        self.assertEqual(codigos, [f'MA04 OA {n:02d}' for n in range(1, 28)])
        for oa in datos['objetivos']:
            with self.subTest(oa=oa['codigo']):
                self.assertTrue(oa['texto'] and oa['indicadores'])
                self.assertTrue(1 <= oa['pagina_indicadores'] <= 194)
                self.assertNotIn('/f_i', oa['texto'] + ' '.join(oa['indicadores']))

    def test_oa_8_es_el_texto_oficial(self):
        # El OA de fracciones de 4° habla de representaciones diferentes; "equivalentes" no es parte de su texto.
        oa = curriculo.objetivo('MA04 OA 08')
        self.assertIn('mostrando que una fracción puede tener representaciones diferentes', oa['texto'])
        self.assertIn('1/100, 1/8, 1/5, 1/4, 1/2', oa['texto'])
        self.assertNotIn('equivalentes', oa['texto'])
        self.assertEqual(oa['pagina_indicadores'], 102)

    def test_busqueda_por_nombre_insensible_a_tildes_y_otros_cursos(self):
        self.assertIsNotNone(curriculo.catalogo('matematica', 'BASICA', '4'))
        self.assertIsNone(curriculo.catalogo('Historia', 'BASICA', 4))
        self.assertIsNone(curriculo.catalogo('Matemática', 'BASICA', 'x'))

    def test_fragmento_lleva_texto_indicadores_y_nota(self):
        f = curriculo.fragmento(curriculo.objetivo('MA04 OA 11'))
        self.assertEqual(f['metodo_recuperacion'], curriculo.METODO)
        self.assertIn('Indicadores de evaluación sugeridos', f['texto'])
        self.assertIn('Nota de revisión', f['texto'])
        self.assertTrue(curriculo.es_oficial([{'metodo_recuperacion': 'textual_biblioteca'}, f]))
        self.assertFalse(curriculo.es_oficial([{'metodo_recuperacion': 'textual_biblioteca'}]))

    def test_texto_objetivo_con_foco(self):
        oa = curriculo.objetivo('MA04 OA 08')
        self.assertEqual(curriculo.texto_objetivo(oa), f"MA04 OA 08: {oa['texto']}")
        self.assertTrue(curriculo.texto_objetivo(oa, ' comparar ').endswith('Foco del docente: comparar'))

    def test_paginas_generales_se_excluyen(self):
        self.assertTrue(biblioteca.es_general('IMPORTANTE En el presente documento, se utilizan de manera '
                                              'inclusiva términos como “el docente”'))
        self.assertTrue(biblioteca.es_general('Índice Presentación 8 Nociones básicas 10'))
        self.assertFalse(biblioteca.es_general('Reconocen fracciones unitarias en figuras geométricas.'))


class FormularioOATests(AsistenteIATestBase):
    datos = {'tema': 'fracciones', 'cantidad': 4, 'cantidad_desarrollo': 0, 'dificultad': 'media'}

    def formulario(self, **cambios):
        return FormularioPrueba({'carga': self.carga.pk, **self.datos, **cambios}, docente=self.docente)

    def test_ofrece_los_oa_del_curso(self):
        opciones = dict(FormularioPrueba(docente=self.docente).fields['oa'].choices)
        grupo = dict(opciones['Matemática · 4° básico'])
        self.assertEqual(len(grupo), 27)
        self.assertIn('MA04 OA 08', grupo)

    def test_oa_elegido_reemplaza_el_objetivo_y_guarda_el_foco(self):
        form = self.formulario(oa='MA04 OA 08', objetivo='comparar fracciones')
        self.assertTrue(form.is_valid(), form.errors)
        self.assertTrue(form.cleaned_data['objetivo'].startswith('MA04 OA 08: Demostrar que comprende'))
        self.assertTrue(form.cleaned_data['objetivo'].endswith('Foco del docente: comparar fracciones'))
        self.assertEqual(form.cleaned_data['foco'], 'comparar fracciones')

    def test_objetivo_personalizado_sigue_funcionando(self):
        form = self.formulario(objetivo='Mi objetivo')
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual((form.cleaned_data['oa'], form.cleaned_data['objetivo']), ('', 'Mi objetivo'))

    def test_rechaza_un_oa_inexistente(self):
        self.assertFalse(self.formulario(oa='MA05 OA 99').is_valid())

    def test_recuperar_trabajo_muestra_solo_el_foco(self):
        form = FormularioPrueba(docente=self.docente, initial={'oa': 'MA04 OA 08', 'foco': 'comparar',
                                                                'objetivo': 'MA04 OA 08: texto largo'})
        self.assertEqual(form.initial['objetivo'], 'comparar')

    def test_fragmentos_docentes_ponen_primero_el_oa_y_quitan_la_lista_de_oa(self):
        from unittest import mock
        from .views_ia import _fragmentos_docentes
        encontrados = [{'pagina': 44, 'texto': 'lista de OA', 'titulo': 'P', 'url': ''},
                       {'pagina': 102, 'texto': 'OA 8 indicadores', 'titulo': 'P', 'url': ''}]
        contexto = {'asignatura': 'Matemática', 'nivel': '4° básico'}
        with mock.patch('colegio.views_ia.proveedor_activo', return_value='qwen'), \
                mock.patch('colegio.views_ia.biblioteca.recuperar', return_value=encontrados):
            fragmentos = _fragmentos_docentes(contexto, {'oa': 'MA04 OA 08', 'carga': self.carga,
                                                          'objetivo': 'x', 'tema': 'fracciones'})
        self.assertEqual(fragmentos[0]['metodo_recuperacion'], curriculo.METODO)
        self.assertEqual([f['pagina'] for f in fragmentos[1:]], [102])

    def test_prueba_generada_con_oa_queda_marcada_como_oficial(self):
        self.client.force_login(self.usuario_docente)
        self.client.post(reverse('ia_crear_prueba'), {'carga': self.carga.pk, 'oa': 'MA04 OA 08', **self.datos})
        prueba = InstrumentoIA.objects.get(tipo=InstrumentoIA.TIPO_PRUEBA)
        self.assertTrue(prueba.objetivo.startswith('MA04 OA 08:'))
        self.assertFalse(prueba.contenido['objetivo_personalizado'])
        self.assertEqual(prueba.contenido['fuentes'][0]['metodo'], curriculo.METODO)
