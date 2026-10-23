"""Conexiones de usuario: aislamiento, cifrado y errores sin revelar secretos."""
import json
import tempfile
from pathlib import Path
from unittest import mock
from concurrent.futures import ThreadPoolExecutor
from django.test import Client, SimpleTestCase, override_settings
from django.urls import reverse
from django.contrib.sessions.models import Session
from .tests import TestCase
from .models import Usuario
from .ia.configuracion import (CLAVE_SESION, leer_conexiones, usar_configuraciones, valor, _cifrador)
from .ia.forms_conexion import ConexionIAForm
from .ia.proveedor import ErrorIA

CLAVE = 'secreto-personal-de-prueba-no-real'
URL = 'https://dashscope-intl.aliyuncs.com/compatible-mode/v1'


class FormularioConexionTests(SimpleTestCase):
    def test_endpoint_restringe_host_https_puerto_y_parametros(self):
        for url in ('http://dashscope-intl.aliyuncs.com/compatible-mode/v1',
                    'https://127.0.0.1/compatible-mode/v1', 'https://example.com/compatible-mode/v1',
                    URL + '?key=secreto', URL.replace('https://', 'https://secreto@'),
                    URL.replace('.com/', '.com:8443/'), URL.replace('/compatible-mode/v1', '/otro')):
            f = ConexionIAForm({'api_key': CLAVE, 'model': 'qwen3.8-flash', 'base_url': url}, proveedor='qwen')
            self.assertFalse(f.is_valid(), url)
        for url in (URL, 'https://workspace.maas.aliyuncs.com/compatible-mode/v1/'):
            self.assertTrue(ConexionIAForm({'api_key': CLAVE, 'model': 'qwen3.8-flash', 'base_url': url}, proveedor='qwen').is_valid())

    @override_settings(QWEN_API_KEY='servidor')
    def test_contextos_concurrentes_no_comparten_claves(self):
        def obtener(clave):
            with usar_configuraciones({'qwen': {'api_key': clave}}):
                return valor('qwen', 'api_key')
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(list(pool.map(obtener, ['uno', 'dos'])), ['uno', 'dos'])
        self.assertEqual(valor('qwen', 'api_key'), 'servidor')

    def test_tutor_y_curricular_usan_clave_personal_gemini(self):
        from .ia.rag import _cliente_embeddings
        from .ia.tutor.embeddings import obtener_cliente
        with usar_configuraciones({'gemini': {'api_key': CLAVE}}), mock.patch('google.genai.Client') as cliente:
            _cliente_embeddings(); obtener_cliente()
        self.assertEqual([c.kwargs['api_key'] for c in cliente.call_args_list], [CLAVE, CLAVE])


@override_settings(IA_PROVEEDOR='gemini', QWEN_API_KEY='servidor-qwen', GEMINI_API_KEY='servidor-gemini')
class ConexionVistaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.docente = Usuario.objects.create_user(username='conexion-docente', rut='1-9', tipo_usuario='DOCENTE')
        cls.otro = Usuario.objects.create_user(username='conexion-otro', rut='2-7', tipo_usuario='DOCENTE')
        cls.apoderado = Usuario.objects.create_user(username='conexion-apoderado', rut='3-5', tipo_usuario='APODERADO')

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.config = override_settings(IA_CREDENCIALES_ARCHIVO=str(Path(self.temp.name) / 'secreto.key'))
        self.config.enable(); self.addCleanup(self.config.disable)
        self.client = Client(SERVER_NAME='localhost')
        self.client.force_login(self.docente)
        self.url = reverse('configurar_conexion_ia', args=['qwen'])
        self.datos = {'qwen-api_key': CLAVE, 'qwen-model': 'qwen-personal', 'qwen-base_url': URL}

    def conectar(self, cliente=None):
        with mock.patch('colegio.ia.views_proveedores.generar', return_value={'estado': 'ok'}):
            return (cliente or self.client).post(self.url, self.datos)

    def test_guarda_cifrada_y_nunca_devuelve_clave(self):
        self.assertEqual(self.conectar().status_code, 302)
        sesion = self.client.session
        self.assertEqual(sesion['ia_proveedor'], 'qwen')
        self.assertNotIn(CLAVE, json.dumps(sesion[CLAVE_SESION]))
        registro_sesion = Session.objects.get(session_key=sesion.session_key)
        self.assertNotIn(CLAVE, json.dumps(registro_sesion.get_decoded()))
        pagina = self.client.get(reverse('registro_ia'))
        self.assertContains(pagina, 'Tu conexión personal')
        self.assertContains(pagina, 'qwen-personal')
        self.assertNotContains(pagina, CLAVE)
        self.assertNotContains(pagina, 'servidor-qwen')
        self.assertNotContains(pagina, 'value="' + CLAVE + '"')

    def test_error_no_guarda_ni_muestra_la_clave_y_mantiene_conexion_anterior(self):
        self.conectar()
        previo = self.client.session[CLAVE_SESION]
        self.datos['qwen-api_key'] = 'clave-erronea-nunca-mostrar'
        with mock.patch('colegio.ia.views_proveedores.generar', side_effect=RuntimeError(self.datos['qwen-api_key'])):
            respuesta = self.client.post(self.url, self.datos)
        self.assertEqual(respuesta.status_code, 400)
        self.assertNotContains(respuesta, self.datos['qwen-api_key'], status_code=400)
        self.assertEqual(self.client.session[CLAVE_SESION], previo)

    def test_api_usa_clave_y_modelo_personales_y_otro_usuario_usa_servidor(self):
        self.conectar()
        from .ia.configuracion import leer_conexiones
        from types import SimpleNamespace
        propias = leer_conexiones(SimpleNamespace(user=self.docente, session=self.client.session))
        respuesta = mock.Mock(status_code=200)
        respuesta.json.return_value = {'choices':[{'message':{'content':'{"estado":"ok"}'}}]}
        cliente_http = mock.MagicMock(); cliente_http.__enter__.return_value.post.return_value = respuesta
        from .ia.proveedor import generar
        from .ia.ejecucion import usar_proveedor
        with usar_configuraciones(propias), usar_proveedor('qwen'), mock.patch('colegio.ia.qwen.httpx.Client', return_value=cliente_http):
            generar('JSON', [], ejemplo={}, formato_json=True)
        llamada = cliente_http.__enter__.return_value.post.call_args
        self.assertEqual(llamada.kwargs['headers']['Authorization'], 'Bearer ' + CLAVE)
        self.assertEqual(llamada.kwargs['json']['model'], 'qwen-personal')
        otro = Client(); otro.force_login(self.otro)
        pagina = otro.get(reverse('registro_ia'))
        self.assertNotContains(pagina, 'qwen-personal')
        self.assertEqual(valor('qwen', 'api_key'), 'servidor-qwen')

    def test_blob_copiado_no_sirve_en_otra_sesion_del_mismo_usuario(self):
        self.conectar()
        otro = Client(); otro.force_login(self.docente)
        sesion = otro.session; sesion[CLAVE_SESION] = self.client.session[CLAVE_SESION]; sesion.save()
        pagina = otro.get(reverse('registro_ia'))
        self.assertContains(pagina, 'Conexión personal caducada o no disponible')

    def test_caducada_bloquea_clave_sin_fallback_y_puede_restablecerse(self):
        self.conectar()
        with mock.patch('colegio.ia.configuracion._cifrador') as cifrador:
            from cryptography.fernet import InvalidToken
            cifrador.return_value.decrypt.side_effect = InvalidToken()
            from types import SimpleNamespace
            propias = leer_conexiones(SimpleNamespace(user=self.docente, session=self.client.session))
            with usar_configuraciones(propias):
                self.assertEqual(valor('qwen', 'api_key'), '')
        self.assertEqual(self.client.post(self.url, {'accion': 'servidor'}).status_code, 302)
        self.assertNotIn('qwen', self.client.session[CLAVE_SESION])

    def test_sesion_cookies_no_admitida_y_ttl_real(self):
        from cryptography.fernet import InvalidToken
        with override_settings(SESSION_ENGINE='django.contrib.sessions.backends.signed_cookies'):
            with self.assertRaises(ValueError): _cifrador(crear=True)
        cifrador = _cifrador(crear=True)
        token = cifrador.encrypt_at_time(b'datos', current_time=100)
        with self.assertRaises(InvalidToken):
            cifrador.decrypt_at_time(token, ttl=28800, current_time=28901)

    def test_endpoint_y_csrf_y_rol_no_envian_clave_al_proveedor(self):
        csrf = Client(enforce_csrf_checks=True); csrf.force_login(self.docente)
        with mock.patch('colegio.ia.views_proveedores.generar') as api:
            self.assertEqual(csrf.post(self.url, self.datos).status_code, 403)
            self.datos['qwen-base_url'] = 'https://example.com/compatible-mode/v1'
            self.assertEqual(self.client.post(self.url, self.datos).status_code, 400)
            self.client.force_login(self.apoderado)
            self.assertEqual(self.client.post(self.url, self.datos).status_code, 403)
        api.assert_not_called()

    def test_gemini_personal_no_hereda_modelos_respaldo_del_servidor(self):
        url = reverse('configurar_conexion_ia', args=['gemini'])
        with mock.patch('colegio.ia.views_proveedores.generar', return_value={'estado':'ok'}):
            self.assertEqual(self.client.post(url, {'gemini-api_key': CLAVE, 'gemini-model':'gemini-personal'}).status_code, 302)
        from types import SimpleNamespace
        configuracion = leer_conexiones(SimpleNamespace(user=self.docente, session=self.client.session))
        self.assertEqual(configuracion['gemini']['modelos_respaldo'], [])
        self.assertEqual(configuracion['gemini']['api_key'], CLAVE)

    @override_settings(ALLOWED_HOSTS=['edugestor.test'])
    def test_fuera_de_loopback_exige_https(self):
        with mock.patch('colegio.ia.views_proveedores.generar', return_value={'estado': 'ok'}) as api:
            cliente = Client(SERVER_NAME='edugestor.test'); cliente.force_login(self.docente)
            self.assertEqual(cliente.post(self.url, self.datos).status_code, 403)
            api.assert_not_called()
            self.assertEqual(cliente.post(self.url, self.datos, secure=True).status_code, 302)

    def test_logout_elimina_conexion_personal(self):
        self.conectar()
        self.client.logout()
        self.assertNotIn(CLAVE_SESION, self.client.session)
