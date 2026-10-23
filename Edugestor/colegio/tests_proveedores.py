"""Pruebas de integración y aislamiento de proveedores, sin servicios externos."""
import json
import tempfile
from pathlib import Path
from unittest import mock
from concurrent.futures import ThreadPoolExecutor
from django.conf import settings
from django.test import TestCase, SimpleTestCase, override_settings, Client
from django.urls import reverse
from .tests import AsistenteIATestBase
from .models import RegistroIA, DocumentoCurricular, FragmentoCurricular
from .ia.proveedor import generar, ErrorIA, proveedor_activo
from .ia.ejecucion import usar_proveedor
from .ia import qwen, rag
from .ia.indice_qwen import reindexar_qwen, estado_indices, huella, exigir_indice_completo

VECTOR = [1.0]+[0.0]*767
OTRO = [0.0,1.0]+[0.0]*766

@override_settings(QWEN_API_KEY='clave-prueba-no-real',QWEN_MODEL='qwen3.8-flash',QWEN_EMBEDDING_MODEL='text-embedding-v4',QWEN_BASE_URL='https://dashscope-intl.aliyuncs.com/compatible-mode/v1')
class AdaptadorQwenTests(SimpleTestCase):
    def test_json_y_adjuntos_se_envian_sin_cambiar_de_proveedor(self):
        respuesta={'choices':[{'message':{'content':'{"respuestas": []}'}}]}
        with usar_proveedor('qwen'), mock.patch('colegio.ia.qwen.solicitar',return_value=respuesta) as enviar, mock.patch('colegio.ia.proveedor._generar_gemini') as gemini:
            resultado=generar('Leer respuestas',[{'rol':'usuario','texto':'Prueba JSON','archivos':[(b'foto','image/png'),(b'pdf','application/pdf')]}],ejemplo={},formato_json=True)
        self.assertEqual(resultado,{'respuestas':[]})
        cuerpo=enviar.call_args.args[1]
        self.assertEqual(cuerpo['response_format'],{'type':'json_object'})
        partes=cuerpo['messages'][1]['content']
        self.assertEqual(partes[0]['type'],'image_url')
        self.assertEqual(partes[1]['file']['file_data'],'data:application/pdf;base64,cGRm')
        gemini.assert_not_called()

    def test_json_invalido_y_error_no_caen_en_gemini(self):
        with usar_proveedor('qwen'),mock.patch('colegio.ia.qwen.solicitar',return_value={'choices':[{'message':{'content':'no es JSON'}}]}),mock.patch('colegio.ia.proveedor._generar_gemini') as otro:
            with self.assertRaises(ErrorIA):generar('JSON',[],ejemplo={},formato_json=True)
        otro.assert_not_called()

    @override_settings(QWEN_API_KEY='')
    def test_sin_clave_es_error_explicito(self):
        with self.assertRaisesMessage(ErrorIA,'QWEN_API_KEY'):
            qwen.solicitar('chat/completions',{})

    def test_error_http_no_revela_clave_ni_archivos(self):
        cliente=mock.MagicMock()
        cliente.__enter__.return_value.post.side_effect=RuntimeError('clave-prueba-no-real data:image/png;base64,FOTO-SECRETA')
        with mock.patch('colegio.ia.qwen.httpx.Client',return_value=cliente):
            with self.assertRaises(ErrorIA) as error:qwen.solicitar('chat/completions',{})
        self.assertNotIn('clave-prueba',str(error.exception))
        self.assertNotIn('FOTO-SECRETA',str(error.exception))

    def test_embedding_dimension_orden_y_no_finitos(self):
        with mock.patch('colegio.ia.qwen.solicitar',return_value={'data':[{'index':0,'embedding':VECTOR}]}):
            self.assertEqual(qwen.embeddings(['texto'],tipo='RETRIEVAL_DOCUMENT'),[VECTOR])
        for vector in ([1.0]*767,[float('nan')]*768,[0.0]*768):
            with mock.patch('colegio.ia.qwen.solicitar',return_value={'data':[{'index':0,'embedding':vector}]}):
                with self.assertRaises(ErrorIA):qwen.embeddings(['texto'],tipo='RETRIEVAL_QUERY')

    def test_contextos_no_se_mezclan(self):
        def activo(nombre):
            with usar_proveedor(nombre):return proveedor_activo()
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(list(pool.map(activo,['qwen','gemini'])),['qwen','gemini'])

class ProveedoresVistaTests(AsistenteIATestBase):
    def setUp(self):
        super().setUp();self.client.force_login(self.usuario_docente)

    def test_selector_persiste_y_rechaza_redirect_externo(self):
        respuesta=self.client.post(reverse('seleccionar_proveedor_ia'),{'proveedor':'qwen','next':'https://externo.test'})
        self.assertRedirects(respuesta,reverse('registro_ia'))
        self.assertEqual(self.client.session['ia_proveedor'],'qwen')
        self.assertEqual(self.client.post(reverse('seleccionar_proveedor_ia'),{'proveedor':'desconocido'}).status_code,400)

    def test_selector_requiere_csrf(self):
        cliente=Client(enforce_csrf_checks=True);cliente.force_login(self.usuario_docente)
        self.assertEqual(cliente.post(reverse('seleccionar_proveedor_ia'),{'proveedor':'qwen'}).status_code,403)

    def test_formulario_qwen_registra_sin_guardar_prompt(self):
        with mock.patch('colegio.ia.qwen.generar',return_value='# Material\nTexto educativo'):
            respuesta=self.client.post(reverse('ia_crear_material'),{'proveedor':'qwen','carga':self.carga.pk,'tema':'Contenido privado no persistir','tipo':'guia','objetivo':'OA'})
        self.assertEqual(respuesta.status_code,302)
        registro=RegistroIA.objects.get(usuario=self.usuario_docente)
        self.assertEqual((registro.proveedor,registro.estado),('qwen','OK'))
        self.assertNotIn('Contenido privado',json.dumps(registro.archivos)+registro.huella_entrada+registro.detalle)
        self.assertEqual(registro.caracteres_salida,len('# Material\nTexto educativo'))

    def test_errores_rag_se_registran(self):
        self.client.post(reverse('ia_crear_prueba'),{'proveedor':'qwen','carga':self.carga.pk,'tema':'Sumas','cantidad':3,'dificultad':'media'})
        registro=RegistroIA.objects.get(usuario=self.usuario_docente)
        self.assertEqual(registro.estado,'ERROR')
        self.assertIn('incompleto',registro.detalle)

    def test_registro_solo_del_usuario(self):
        registro=RegistroIA.objects.create(usuario=self.usuario_otro_docente,proveedor='qwen',operacion='Privada',estado='OK')
        self.assertEqual(self.client.get(reverse('detalle_registro_ia',args=[registro.pk])).status_code,404)
        respuesta=self.client.get(reverse('registro_ia'))
        self.assertNotContains(respuesta,'Privada')
        self.assertNotContains(respuesta,'GEMINI_API_KEY=')

    def test_tutor_simulado_no_llama_embeddings(self):
        self.client.force_login(self.usuario_alumno)
        with mock.patch('colegio.ia.tutor.rag_service.recuperar_contexto') as recuperar:
            self.client.post(reverse('tutor_alumno'),{'asignatura':self.asignatura.pk,'mensaje':'Hola'})
        recuperar.assert_not_called()

@override_settings(QWEN_EMBEDDING_MODEL='text-embedding-v4')
class IndicesSeparadosTests(TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.override=override_settings(BASE_DIR=Path(self.temp.name));self.override.enable();self.addCleanup(self.override.disable)
        carpeta=Path(self.temp.name)/'knowledge/procesados';carpeta.mkdir(parents=True)
        (carpeta/'libro_matematica_embeddings.json').write_text(json.dumps([{'id':'uno','pagina':1,'texto':'Sumas','embedding':VECTOR}]))
        d=DocumentoCurricular.objects.create(titulo='Matemática',asignatura='Matemática',ciclo='BASICA',nivel=1,sha256='a'*64)
        self.a=FragmentoCurricular.objects.create(documento=d,numero=1,pagina=1,texto='Sumas',embedding=VECTOR)
        self.b=FragmentoCurricular.objects.create(documento=d,numero=2,pagina=2,texto='Restas',embedding=OTRO)

    def completar(self):
        with mock.patch('colegio.ia.qwen.embeddings',side_effect=lambda textos,**kw:[OTRO for _ in textos]):
            return reindexar_qwen()

    def test_migracion_preserva_gemini_y_reindexacion_repetible(self):
        self.assertIsNone(self.a.embedding_qwen)
        self.assertTrue(self.completar()['completo'])
        self.a.refresh_from_db();self.assertEqual(list(self.a.embedding),VECTOR)
        self.assertEqual(list(self.a.embedding_qwen),OTRO)
        with mock.patch('colegio.ia.qwen.embeddings') as api:
            self.assertTrue(reindexar_qwen()['completo'])
        api.assert_not_called()

    def test_consultas_usan_indices_independientes(self):
        self.completar()
        self.b.embedding_qwen=VECTOR;self.b.save(update_fields=['embedding_qwen'])
        with mock.patch('colegio.ia.rag.crear_embeddings',return_value=[VECTOR]):
            with usar_proveedor('gemini'):
                gemini=rag.buscar_fragmentos(consulta='suma',asignatura='Matemática',ciclo='BASICA',nivel=1)
            with usar_proveedor('qwen'):
                q=rag.buscar_fragmentos(consulta='suma',asignatura='Matemática',ciclo='BASICA',nivel=1)
        self.assertEqual(gemini[0]['pagina'],1);self.assertEqual(q[0]['pagina'],2)

    def test_cambio_modelo_texto_o_indice_parcial_bloquea_qwen(self):
        with self.assertRaises(ErrorIA):exigir_indice_completo()
        self.completar()
        with override_settings(QWEN_EMBEDDING_MODEL='otro-modelo'):
            self.assertFalse(estado_indices()['completo'])
        self.a.texto='Texto nuevo';self.a.save(update_fields=['texto'])
        self.assertFalse(estado_indices()['completo'])

    def test_error_de_lote_permite_reanudar_sin_borrar_gemini(self):
        with mock.patch('colegio.ia.qwen.embeddings',side_effect=[ [OTRO,OTRO], ErrorIA('Sin cuota') ]):
            with self.assertRaises(ErrorIA):reindexar_qwen()
        self.a.refresh_from_db();self.assertEqual(list(self.a.embedding),VECTOR)
        self.assertFalse(estado_indices()['completo'])
        self.assertTrue(self.completar()['completo'])
