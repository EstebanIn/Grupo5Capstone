"""Catálogos por conexión, paginación, selección y protección de credenciales."""
from unittest import mock
from django.core.cache import cache
from django.test import SimpleTestCase, Client, override_settings
from django.urls import reverse
from .tests import TestCase
from .models import Usuario
from .ia.catalogo_modelos import listar_modelos
from .ia.proveedor import ErrorIA
from .ia.forms_conexion import ConexionIAForm

URL = 'https://dashscope-intl.aliyuncs.com/compatible-mode/v1'
OTRA_URL = 'https://workspace.cn-beijing.maas.aliyuncs.com/compatible-mode/v1'
CLAVE = 'secreto-catalogo-no-real'


def respuesta(datos, status=200):
    objeto = mock.Mock(status_code=status)
    objeto.json.return_value = datos
    return objeto


def qwen_fila(modelo='qwen3.8-flash', imagenes=True, **cambios):
    return {'model': modelo, 'name': modelo.replace('qwen', 'Qwen', 1), 'provider': 'qwen',
            'capabilities': ['TG'], 'inference_metadata': {'request_modality': ['Text', 'Image'] if imagenes else ['Text'],
            'response_modality': ['Text']}, **cambios}


class CatalogoModelosTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.http = mock.MagicMock()
        self.parche = mock.patch('colegio.ia.catalogo_modelos.httpx.Client', return_value=self.http)
        self.parche.start(); self.addCleanup(self.parche.stop)
        self.get = self.http.__enter__.return_value.get

    def test_qwen_pagina_filtra_modalidades_y_mantiene_orden(self):
        self.get.side_effect = [
            respuesta({'output': {'total': 5, 'models': [qwen_fila('qwen3.8-max'), qwen_fila('text-embedding-v4', capabilities=['TR'])]}}),
            respuesta({'output': {'total': 5, 'models': [qwen_fila('qwen3.8-flash'), qwen_fila('qwen3.8-max'),
                qwen_fila('qwen-image', inference_metadata={'response_modality': ['Image']})]}})]
        datos = listar_modelos('qwen', api_key=CLAVE, base_url=URL)
        self.assertEqual([m['id'] for m in datos['modelos']], ['qwen3.8-max', 'qwen3.8-flash'])
        self.assertTrue(datos['modelos'][0]['imagenes'])
        self.assertEqual(self.get.call_args_list[1].kwargs['params']['page_no'], 2)
        for llamada in self.get.call_args_list:
            self.assertEqual(llamada.args[0], 'https://dashscope-intl.aliyuncs.com/api/v1/models')
            self.assertNotIn(CLAVE, llamada.args[0])
            self.assertEqual(llamada.kwargs['headers']['Authorization'], 'Bearer ' + CLAVE)
        self.assertNotIn(CLAVE, str(datos))

    def test_gemini_pagina_y_excluye_audio_imagen_embedding_y_otras_familias(self):
        def fila(nombre, metodos=None):
            return {'name': 'models/' + nombre, 'displayName': nombre, 'supportedGenerationMethods': metodos or ['generateContent']}
        self.get.side_effect = [respuesta({'models': [fila('gemini-flash-latest'), fila('gemini-tts-preview'),
            fila('gemini-embedding-001', ['embedContent']), fila('gemini-3.5-transcribe'), fila('gemma-4-31b-it')], 'nextPageToken': 'segunda'}),
            respuesta({'models': [fila('gemini-flash-lite-latest'), fila('gemini-image-preview')]})]
        datos = listar_modelos('gemini', api_key=CLAVE)
        self.assertEqual([m['id'] for m in datos['modelos']], ['gemini-flash-latest', 'gemini-flash-lite-latest'])
        self.assertEqual(self.get.call_args.kwargs['params']['pageToken'], 'segunda')
        self.assertEqual(self.get.call_args.kwargs['headers']['x-goog-api-key'], CLAVE)
        self.assertNotIn(CLAVE, self.get.call_args.args[0])

    def test_cache_separa_clave_endpoint_y_proveedor(self):
        self.get.return_value = respuesta({'output': {'total': 1, 'models': [qwen_fila()]}})
        listar_modelos('qwen', api_key=CLAVE, base_url=URL)
        listar_modelos('qwen', api_key=CLAVE, base_url=URL)
        self.assertEqual(self.get.call_count, 1)
        listar_modelos('qwen', api_key='otra-clave', base_url=URL)
        listar_modelos('qwen', api_key=CLAVE, base_url=OTRA_URL)
        self.assertEqual(self.get.call_count, 3)
        self.get.return_value = respuesta({'models': [{'name':'models/gemini-flash-latest', 'supportedGenerationMethods':['generateContent']}]})
        listar_modelos('gemini', api_key=CLAVE)
        self.assertEqual(self.get.call_count, 4)

    def test_errores_no_revelan_respuesta_clave_ni_cachean_fallos(self):
        for status in (401, 403, 429, 500):
            self.get.return_value = respuesta({'error': CLAVE}, status=status)
            with self.assertRaises(ErrorIA) as error:
                listar_modelos('qwen', api_key=CLAVE, base_url=URL)
            self.assertNotIn(CLAVE, str(error.exception))
        self.get.side_effect = RuntimeError(CLAVE)
        with self.assertRaises(ErrorIA) as error:
            listar_modelos('qwen', api_key=CLAVE, base_url=URL)
        self.assertNotIn(CLAVE, str(error.exception))
        self.assertEqual(self.get.call_count, 5)

    def test_catalogo_parcial_o_bucle_no_se_presenta_como_completo(self):
        self.get.side_effect = [respuesta({'output': {'total': 2, 'models': [qwen_fila()]}}),
                               respuesta({'output': {'total': 2, 'models': []}})]
        with self.assertRaises(ErrorIA): listar_modelos('qwen', api_key=CLAVE, base_url=URL)
        self.get.side_effect = None
        self.get.return_value = respuesta({'models': [{'name':'models/gemini-flash-latest', 'supportedGenerationMethods':['generateContent']}], 'nextPageToken': 'repetido'})
        with self.assertRaises(ErrorIA): listar_modelos('gemini', api_key=CLAVE)

    def test_select_conserva_modelo_configurado_y_valida_identificador(self):
        f = ConexionIAForm(proveedor='qwen', prefix='qwen', initial={'model': 'qwen-personal'})
        self.assertIn('<select', str(f['model']))
        self.assertIn('value="qwen-personal" selected', str(f['model']))
        f = ConexionIAForm({'api_key':CLAVE, 'base_url': URL, 'model':'<script>'}, proveedor='qwen')
        self.assertFalse(f.is_valid())


@override_settings(IA_PROVEEDOR='gemini', QWEN_API_KEY='clave-servidor', QWEN_BASE_URL=URL, GEMINI_API_KEY='gemini-servidor')
class CatalogoVistaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.usuario = Usuario.objects.create_user(username='catalogo-docente', rut='1-9', tipo_usuario='DOCENTE')
        cls.apoderado = Usuario.objects.create_user(username='catalogo-apoderado', rut='2-7', tipo_usuario='APODERADO')

    def setUp(self):
        self.client = Client(SERVER_NAME='localhost'); self.client.force_login(self.usuario)
        self.url = reverse('consultar_modelos_ia', args=['qwen'])
        self.resultado = {'proveedor':'qwen', 'modelos':[{'id':'qwen3.8-flash','nombre':'Qwen3.8-Flash','imagenes':True}], 'actualizado':'2026-10-23T19:00:00+00:00'}

    def test_carga_automatica_usa_conexion_actual_y_no_envia_campos_en_edicion(self):
        with mock.patch('colegio.ia.catalogo_modelos.listar_modelos', return_value=self.resultado) as listar:
            r = self.client.post(self.url, {'usar_actual':'1','qwen-api_key':CLAVE,'qwen-base_url': OTRA_URL})
        self.assertEqual(r.status_code, 200)
        listar.assert_called_once_with('qwen', api_key='clave-servidor', base_url=URL)
        self.assertNotIn('clave-servidor', r.content.decode())
        self.assertIn('no-store', r.headers['Cache-Control'])
        self.assertNotIn('ia_conexiones', self.client.session)
        self.assertNotIn('ia_proveedor', self.client.session)

    def test_clave_nueva_y_workspace_se_consultan_sin_guardar(self):
        with mock.patch('colegio.ia.catalogo_modelos.listar_modelos', return_value=self.resultado) as listar:
            r = self.client.post(self.url, {'qwen-api_key':CLAVE, 'qwen-base_url':OTRA_URL})
        self.assertEqual(r.status_code, 200)
        listar.assert_called_once_with('qwen', api_key=CLAVE, base_url=OTRA_URL)
        self.assertNotIn('ia_conexiones', self.client.session)

    def test_clave_guardada_no_se_reenvia_a_otro_workspace(self):
        with mock.patch('colegio.ia.catalogo_modelos.listar_modelos') as listar:
            r = self.client.post(self.url, {'qwen-base_url':OTRA_URL})
        self.assertEqual(r.status_code, 400); listar.assert_not_called()

    def test_rechaza_url_externa_csrf_y_rol_sin_consultar_proveedor(self):
        csrf = Client(enforce_csrf_checks=True, SERVER_NAME='localhost'); csrf.force_login(self.usuario)
        with mock.patch('colegio.ia.catalogo_modelos.listar_modelos') as listar:
            self.assertEqual(csrf.post(self.url, {'usar_actual':'1'}).status_code, 403)
            self.assertEqual(self.client.post(self.url, {'qwen-api_key': CLAVE, 'qwen-base_url':'https://example.com/compatible-mode/v1'}).status_code, 400)
            self.client.force_login(self.apoderado)
            self.assertEqual(self.client.post(self.url, {'usar_actual':'1'}).status_code, 403)
        listar.assert_not_called()

    def test_error_inesperado_no_devuelve_datos_privados(self):
        with mock.patch('colegio.ia.catalogo_modelos.listar_modelos', side_effect=RuntimeError(CLAVE)):
            r = self.client.post(self.url, {'usar_actual':'1'})
        self.assertEqual(r.status_code, 502)
        self.assertNotIn(CLAVE, r.content.decode())

    def test_pagina_muestra_ambos_selectores_sin_llamar_api_en_la_vista(self):
        with mock.patch('colegio.ia.catalogo_modelos.listar_modelos') as listar:
            r = self.client.get(reverse('registro_ia'))
        self.assertContains(r, '<select name="qwen-model"')
        self.assertContains(r, '<select name="gemini-model"')
        self.assertContains(r, 'ia-catalogo-actualizar">Actualizar modelos</button>', count=2)
        self.assertNotContains(r, 'clave-servidor')
        listar.assert_not_called()
