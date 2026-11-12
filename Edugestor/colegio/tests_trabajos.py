import json
import tempfile
import uuid
from datetime import timedelta
from pathlib import Path
from unittest import mock

import httpx
from django.test import SimpleTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .tests import AsistenteIATestBase
from .models import TrabajoIA, InstrumentoIA, Institucion
from .ia.trabajos import ejecutar, limpiar, ruta_privada
from .ia.proveedor import ErrorIA
from .ia import qwen
from .tenancy import institucion_activa


class TrabajoTests(AsistenteIATestBase):
    ejecutar_en_pruebas = False

    def setUp(self):
        super().setUp()
        self.client.force_login(self.usuario_docente)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        ajuste = override_settings(IA_ARCHIVOS_PRIVADOS=Path(self.temp.name)/'files',
                                   IA_CREDENCIALES_ARCHIVO=str(Path(self.temp.name)/'key'))
        ajuste.enable(); self.addCleanup(ajuste.disable)

    def enviar(self, **cambios):
        datos = {'carga': self.carga.pk, 'tema': 'Multiplicación', 'cantidad': 3, 'dificultad': 'media',
                 'idempotencia': str(uuid.uuid4())}
        datos.update(cambios)
        with self.captureOnCommitCallbacks(execute=True), mock.patch('colegio.ia.trabajos.encolar') as cola:
            respuesta = self.client.post(reverse('ia_crear_prueba'), datos, HTTP_ACCEPT='application/json')
        self.assertEqual(respuesta.status_code, 202)
        return TrabajoIA.objects.get(pk=respuesta.json()['id']), datos, cola

    def test_cola_recibe_solo_identificador_y_doble_envio_no_duplica(self):
        trabajo, datos, _ = self.enviar()
        with mock.patch('colegio.tasks.ejecutar_trabajo.apply_async') as enviar:
            from .ia.trabajos import encolar
            encolar(trabajo.pk)
        self.assertEqual(enviar.call_args.kwargs, {'args': [str(trabajo.pk)], 'retry': False})
        self.client.post(reverse('ia_crear_prueba'), datos)
        self.assertEqual(TrabajoIA.objects.count(), 1)
        ejecutar(trabajo.pk); ejecutar(trabajo.pk)
        trabajo.refresh_from_db()
        self.assertEqual(trabajo.estado, 'completado')
        self.assertEqual(InstrumentoIA.objects.count(), 1)

    def test_sesion_cerrada_no_ejecuta(self):
        trabajo, _, _ = self.enviar()
        self.client.logout()
        ejecutar(trabajo.pk); trabajo.refresh_from_db()
        self.assertEqual(trabajo.estado, 'error')
        self.assertFalse(InstrumentoIA.objects.exists())

    def test_conexion_cambiada_no_consume_otra(self):
        trabajo, _, _ = self.enviar()
        trabajo.conexion_huella = '0'*64; trabajo.save()
        with mock.patch('colegio.ia.asistentes.generar') as generar:
            ejecutar(trabajo.pk)
        generar.assert_not_called()
        trabajo.refresh_from_db(); self.assertEqual(trabajo.estado, 'error')

    def test_otro_docente_y_otra_institucion_no_ven_estado_resultado_archivo(self):
        trabajo, _, _ = self.enviar()
        self.client.force_login(self.usuario_otro_docente)
        for ruta in ('ia_trabajo', 'ia_trabajo_estado', 'ia_trabajo_descargar'):
            self.assertEqual(self.client.get(reverse(ruta, args=[trabajo.pk])).status_code, 404)
        otra = Institucion.objects.create(nombre='Otra', slug='otra')
        with institucion_activa(otra):
            self.assertFalse(TrabajoIA.objects.filter(pk=trabajo.pk).exists())

    def test_permiso_de_carga_se_revalida(self):
        trabajo, _, _ = self.enviar()
        self.carga.docente = self.usuario_otro_docente.docente; self.carga.save()
        ejecutar(trabajo.pk); trabajo.refresh_from_db()
        self.assertEqual(trabajo.estado, 'error')
        self.assertFalse(InstrumentoIA.objects.exists())

    def test_interrumpidos_caducan_y_no_se_reenvian(self):
        trabajo, _, _ = self.enviar()
        TrabajoIA.objects.filter(pk=trabajo.pk).update(estado='generando', creado=timezone.now()-timedelta(minutes=6), iniciado=timezone.now()-timedelta(minutes=6))
        limpiar(); ejecutar(trabajo.pk); trabajo.refresh_from_db()
        self.assertEqual(trabajo.estado, 'error')
        self.assertFalse(InstrumentoIA.objects.exists())

    def test_error_conserva_campos_y_no_filtra_excepcion(self):
        trabajo, _, _ = self.enviar()
        with mock.patch('colegio.ia.asistentes.generar', side_effect=RuntimeError('SECRET-API-PROMPT')):
            ejecutar(trabajo.pk)
        trabajo.refresh_from_db()
        self.assertEqual(trabajo.parametros['tema'], 'Multiplicación')
        self.assertNotIn('SECRET', trabajo.mensaje)
        pagina = self.client.get(reverse('ia_crear_prueba')+'?trabajo='+str(trabajo.pk))
        self.assertContains(pagina, 'Multiplicación')

    def test_adjuntos_cifrados_se_eliminan_en_error(self):
        trabajo, _, _ = self.enviar()
        archivo = ruta_privada(f'{trabajo.pk}-0.bin'); archivo.parent.mkdir(parents=True)
        archivo.write_bytes(b'ciphertext')
        trabajo.temporales = [{'nombre': archivo.name, 'tipo': 'image/png'}]; trabajo.save()
        trabajo.conexion_huella = '0'*64; trabajo.save()
        ejecutar(trabajo.pk); trabajo.refresh_from_db()
        self.assertFalse(archivo.exists()); self.assertEqual(trabajo.temporales, [])


@override_settings(QWEN_API_KEY='synthetic-secret', QWEN_BASE_URL='https://dashscope-intl.aliyuncs.com/compatible-mode/v1')
class StreamingQwenTests(SimpleTestCase):
    def llamar(self, handler):
        cliente = httpx.Client
        transporte = httpx.MockTransport(handler)
        with mock.patch('colegio.ia.qwen.httpx.Client', side_effect=lambda **kw: cliente(transport=transporte, **kw)):
            return qwen.solicitar('chat/completions', {'model': 'modelo-personal', 'messages': []})

    def test_ensambla_stream_sin_exponer_razonamiento(self):
        eventos = [{'choices':[{'delta':{'reasoning_content':'privado'}, 'finish_reason':None}]},
                   {'choices':[{'delta':{'content':'{"a":'}, 'finish_reason':None}]},
                   {'choices':[{'delta':{'content':'1}'}, 'finish_reason':'stop'}]}]
        datos = '\n\n'.join('data: '+json.dumps(e) for e in eventos)+'\n\ndata: [DONE]\n'
        respuesta = self.llamar(lambda r: httpx.Response(200, text=datos))
        self.assertEqual(respuesta['choices'][0]['message']['content'], '{"a":1}')

    def test_stream_truncado_no_reintenta(self):
        llamadas = []
        def responder(r):
            llamadas.append(r)
            return httpx.Response(200, text='data: {"choices":[{"delta":{"content":"parcial"}}]}\n')
        with self.assertRaises(ErrorIA): self.llamar(responder)
        self.assertEqual(len(llamadas), 1)

    def test_categorias_http_sin_cuerpo_privado(self):
        for codigo, categoria in ((401,'autenticacion'), (404,'modelo_no_disponible'), (429,'cuota'), (503,'no_disponible')):
            with self.subTest(codigo=codigo), self.assertRaises(ErrorIA) as error:
                self.llamar(lambda r: httpx.Response(codigo, text='synthetic-secret prompt'))
            self.assertEqual(error.exception.categoria, categoria)
            self.assertNotIn('synthetic-secret', str(error.exception))

    def test_read_timeout_no_repite_solicitud_incierta(self):
        llamadas=[]
        def responder(r):
            llamadas.append(r); raise httpx.ReadTimeout('private body')
        with self.assertRaises(ErrorIA) as error: self.llamar(responder)
        self.assertEqual(error.exception.categoria, 'timeout'); self.assertEqual(len(llamadas),1)
