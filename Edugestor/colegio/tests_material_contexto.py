"""El objetivo personalizado permite generar sin inventar una recuperación RAG."""
import json
from unittest import mock

from django.urls import reverse

from .tests import AsistenteIATestBase
from .models import DocumentoCurricular, FragmentoCurricular, InstrumentoIA, RegistroIA, TrabajoIA


CONTENIDO = json.dumps({'titulo': 'Multiplicación y división',
    'contenido': 'Ejemplo resuelto: 124 × 3 = 372.',
    'ejercicios': 'Calcula 84 ÷ 4.', 'solucionario': '21.'})


class MaterialContextoTests(AsistenteIATestBase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.usuario_docente)
        self.url = reverse('ia_crear_material')
        self.datos = {'proveedor': 'qwen', 'carga': self.carga.pk,
            'tema': 'multiplicaciones y divisiones', 'objetivo': 'Describir estrategias de cálculo', 'tipo': 'guia'}

    def fragmento(self, nivel=4):
        d = DocumentoCurricular.objects.create(titulo='Fuente de prueba', asignatura='Matemática',
            ciclo='BASICA', nivel=nivel, sha256=str(nivel)*64)
        return FragmentoCurricular.objects.create(documento=d, numero=1, texto='Estrategias',
            embedding=[1.0]+[0.0]*767)

    def test_sin_corpus_ofrece_objetivo_personalizado_antes_del_envio(self):
        pagina = self.client.get(self.url)
        self.assertEqual(pagina.context['form'].initial['contexto_curricular'], 'personalizado')
        self.assertContains(pagina, 'No hay fuentes indexadas')

    def test_fuentes_de_otro_nivel_no_se_consideran_cobertura(self):
        self.fragmento(nivel=1)
        self.assertEqual(self.client.get(self.url).context['form'].initial['contexto_curricular'], 'personalizado')

    def test_con_corpus_del_curso_conserva_rag_como_opcion_inicial(self):
        self.fragmento()
        formulario = self.client.get(self.url).context['form']
        self.assertEqual(formulario['contexto_curricular'].value(), 'curricular')

    def test_personalizado_genera_con_qwen_sin_consultar_embeddings(self):
        with mock.patch('colegio.ia.rag.buscar_fragmentos') as buscar, \
             mock.patch('colegio.ia.qwen.generar', return_value=CONTENIDO) as qwen, \
             mock.patch('colegio.ia.proveedor._generar_gemini') as gemini:
            respuesta = self.client.post(self.url, {**self.datos, 'contexto_curricular': 'personalizado'})
        self.assertEqual(respuesta.status_code, 302)
        buscar.assert_not_called(); gemini.assert_not_called(); qwen.assert_called_once()
        trabajo = TrabajoIA.objects.get()
        self.assertEqual((trabajo.estado, trabajo.proveedor), ('completado', 'qwen'))
        self.assertEqual(trabajo.parametros['contexto_curricular'], 'personalizado')
        c = InstrumentoIA.objects.get().contenido
        self.assertEqual(c['fuentes'], []); self.assertFalse(c['rag_aplicado'])
        self.assertTrue(c['objetivo_personalizado'])
        self.assertEqual(RegistroIA.objects.get().proveedor, 'qwen')

    def test_rag_sin_corpus_no_llama_al_modelo_ni_cambia_de_proveedor(self):
        with mock.patch('colegio.ia.qwen.generar') as qwen, \
             mock.patch('colegio.ia.proveedor._generar_gemini') as gemini:
            self.client.post(self.url, {**self.datos, 'contexto_curricular': 'curricular'})
        qwen.assert_not_called(); gemini.assert_not_called()
        trabajo = TrabajoIA.objects.get()
        self.assertEqual(trabajo.estado, 'error')
        self.assertIn('no hay fuentes', trabajo.mensaje)
        self.assertFalse(InstrumentoIA.objects.exists())

    def test_indice_qwen_parcial_sigue_bloqueado_en_modo_rag(self):
        self.fragmento()
        with mock.patch('colegio.ia.qwen.generar') as qwen:
            self.client.post(self.url, {**self.datos, 'contexto_curricular': 'curricular'})
        qwen.assert_not_called()
        self.assertIn('incompleto', TrabajoIA.objects.get().mensaje)

    def test_opcion_invalida_conserva_el_formulario_y_no_encola(self):
        pagina = self.client.post(self.url, {**self.datos, 'contexto_curricular': 'otro'})
        self.assertEqual(pagina.status_code, 200)
        self.assertIn('contexto_curricular', pagina.context['form'].errors)
        self.assertContains(pagina, self.datos['objetivo'])
        self.assertFalse(TrabajoIA.objects.exists())

    def test_rag_gemini_tampoco_continua_si_no_recupera_fuentes(self):
        with mock.patch('colegio.ia.rag.buscar_fragmentos', return_value=[]), \
             mock.patch('colegio.ia.proveedor._generar_gemini') as generar:
            self.client.post(self.url, {**self.datos, 'proveedor': 'gemini', 'contexto_curricular': 'curricular'})
        generar.assert_not_called()
        self.assertIn('No se recuperaron fuentes', TrabajoIA.objects.get().mensaje)

    def test_rag_incorpora_solo_las_fuentes_realmente_recuperadas(self):
        fuentes = [{'titulo': 'Currículo de prueba', 'texto': 'Estrategias para multiplicar y dividir',
                    'url': 'https://www.curriculumnacional.cl/', 'pagina': 25}]
        with mock.patch('colegio.ia.rag.buscar_fragmentos', return_value=fuentes) as buscar, \
             mock.patch('colegio.ia.qwen.generar', return_value=CONTENIDO):
            self.client.post(self.url, {**self.datos, 'contexto_curricular': 'curricular'})
        self.assertEqual(buscar.call_args.kwargs['nivel'], 4)
        c = InstrumentoIA.objects.get().contenido
        self.assertTrue(c['rag_aplicado'])
        self.assertEqual(c['fuentes'][0]['pagina'], 25)
