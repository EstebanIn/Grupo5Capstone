"""Integridad, portabilidad, permisos y recuperación compartida sin API real."""
import io
import json
import tempfile
import uuid
import zipfile
from datetime import timedelta
from pathlib import Path
from unittest import mock

from django.test import TestCase, SimpleTestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject

from .ia import biblioteca as b, biblioteca_paquetes as paquetes
from .ia.biblioteca_catalogo import preparar_catalogo
from .ia.ejecucion import usar_proveedor
from .ia.proveedor import ErrorIA
from .models import DocumentoCurricular, FragmentoCurricular, FuenteBiblioteca, TrabajoIA, RegistroIA
from .tests import AsistenteIATestBase


def pdf_prueba(texto='Multiplicacion y division: repartir 84 objetos en 4 grupos da 21 objetos por grupo. '):
    w = PdfWriter(); p = w.add_blank_page(width=595, height=842)
    fuente = DictionaryObject({NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type1'),
                              NameObject('/BaseFont'): NameObject('/Helvetica')})
    p[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): fuente})})
    stream = DecodedStreamObject(); stream.set_data(('BT /F1 12 Tf 30 700 Td ('+texto*4+') Tj ET').encode('ascii'))
    p[NameObject('/Contents')] = w._add_object(stream)
    salida = io.BytesIO(); w.write(salida); return salida.getvalue()


class BibliotecaBase:
    def iniciar_biblioteca(self):
        self.temporal = tempfile.TemporaryDirectory(); self.addCleanup(self.temporal.cleanup)
        ajuste = override_settings(BIBLIOTECA_RAIZ=Path(self.temporal.name)/'biblioteca',
            IA_ARCHIVOS_PRIVADOS=Path(self.temporal.name)/'privados', BIBLIOTECA_BUSQUEDA='textual')
        ajuste.enable(); self.addCleanup(ajuste.disable)
        self.fuente = preparar_catalogo()
        self.pdf = pdf_prueba()

    def sincronizar(self, pdf=None):
        with mock.patch.object(b, 'localizar_pdf', return_value=self.fuente.descarga_url), \
             mock.patch.object(b, 'descargar', return_value=(pdf or self.pdf,self.fuente.descarga_url)):
            return b.sincronizar(self.fuente.pk)


class BibliotecaSeguridadTests(SimpleTestCase):
    def test_solo_https_y_host_exacto_sin_credenciales(self):
        for url in ['http://www.curriculumnacional.cl/a.pdf', 'https://127.0.0.1/a.pdf',
                    'https://www.curriculumnacional.cl.evil.test/a.pdf', 'https://x@www.curriculumnacional.cl/a.pdf',
                    'https://www.curriculumnacional.cl:8080/a.pdf']:
            with self.subTest(url=url), self.assertRaises(ErrorIA): b.url_autorizada(url)

    def test_valida_redireccion_antes_de_solicitar_otro_host(self):
        import httpx
        solicitudes = []
        def responder(request):
            solicitudes.append(str(request.url))
            return httpx.Response(302, headers={'location':'http://127.0.0.1/secreto'})
        cliente = httpx.Client(transport=httpx.MockTransport(responder))
        with mock.patch.object(b.httpx, 'Client', return_value=cliente), self.assertRaises(ErrorIA):
            b.descargar('https://www.curriculumnacional.cl/a.pdf')
        self.assertEqual(len(solicitudes),1)

    def test_descarga_acota_bytes_y_plazo(self):
        import httpx
        for opciones in [{'maximo':3}, {'plazo':1}]:
            cliente = httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(200,content=b'12345')))
            with mock.patch.object(b.httpx,'Client', return_value=cliente), self.assertRaises(ErrorIA):
                b.descargar('https://www.curriculumnacional.cl/a.pdf',**opciones)

    def test_rechaza_html_y_pdf_sin_texto(self):
        with self.assertRaises(ErrorIA): b.extraer(b'<html>error</html>')
        with self.assertRaises(ErrorIA): b.extraer(pdf_prueba(''))


class BibliotecaDatosTests(BibliotecaBase, TestCase):
    def setUp(self): self.iniciar_biblioteca()

    def test_sincroniza_y_no_reprocesa_ni_duplica_sin_cambios(self):
        self.sincronizar()
        f = FragmentoCurricular.objects.get()
        f.embedding_qwen=[1.0]+[0.0]*767; f.save()
        with mock.patch.object(b,'extraer') as extraer:
            self.assertTrue(self.sincronizar()['sin_cambios'])
        extraer.assert_not_called()
        self.assertEqual(DocumentoCurricular.objects.count(),1)
        f.refresh_from_db(); self.assertIsNotNone(f.embedding_qwen)
        self.fuente.refresh_from_db(); self.assertIsNotNone(self.fuente.proxima_revision)

    def test_actualizacion_versionada_conserva_anterior_y_error_no_la_desactiva(self):
        self.sincronizar(); antiguo=DocumentoCurricular.objects.get()
        with self.assertRaises(ErrorIA): self.sincronizar(b'no pdf')
        antiguo.refresh_from_db(); self.assertTrue(antiguo.activo)
        self.sincronizar(pdf_prueba('Division: 48 objetos repartidos en 2 grupos da 24 objetos en cada grupo. '))
        antiguo.refresh_from_db(); self.assertFalse(antiguo.activo)
        self.assertEqual(DocumentoCurricular.objects.count(),2)
        self.assertEqual(DocumentoCurricular.objects.filter(activo=True).count(),1)
        # Una versión anterior puede volver a publicarse sin perder su índice.
        self.sincronizar(); antiguo.refresh_from_db(); self.assertTrue(antiguo.activo)

    def test_bloqueo_y_recuperacion_tras_interrupcion(self):
        self.fuente.bloqueo=uuid.uuid4(); self.fuente.bloqueo_hasta=timezone.now()+timedelta(minutes=3); self.fuente.save()
        with self.assertRaises(ErrorIA): self.sincronizar()
        self.fuente.bloqueo_hasta=timezone.now()-timedelta(seconds=1); self.fuente.save()
        self.sincronizar(); self.fuente.refresh_from_db(); self.assertIsNone(self.fuente.bloqueo)

    def test_reinicio_recupera_fuente_y_limpia_solo_temporales_antiguos(self):
        import os
        self.sincronizar()
        self.fuente.estado='actualizando'; self.fuente.bloqueo=uuid.uuid4()
        self.fuente.bloqueo_hasta=timezone.now()-timedelta(seconds=1); self.fuente.save()
        tmp=b.ruta_original(b.huella(self.pdf)).with_suffix('.interrumpido.tmp'); tmp.write_bytes(b'temporal')
        os.utime(tmp,(1,1)); b.limpiar_interrumpidas()
        self.fuente.refresh_from_db(); self.assertEqual(self.fuente.estado,'error'); self.assertIsNone(self.fuente.bloqueo)
        self.assertFalse(tmp.exists()); self.assertTrue(b.ruta_original(b.huella(self.pdf)).exists())

    def test_busqueda_local_filtra_nivel_y_no_llama_a_proveedores(self):
        self.sincronizar()
        with usar_proveedor('qwen'), mock.patch('colegio.ia.rag.crear_embeddings') as api:
            resultados=b.recuperar(consulta='divisiones',asignatura='Matemática',ciclo='BASICA',nivel=4)
        api.assert_not_called(); self.assertEqual(resultados[0]['pagina'],1)
        self.assertEqual(resultados[0]['metodo_recuperacion'],'textual_biblioteca')
        self.assertEqual(b.buscar_texto(consulta='division',asignatura='Matemática',ciclo='BASICA',nivel=5),[])
        self.assertEqual(b.buscar_texto(consulta='geografia',asignatura='Matemática',ciclo='BASICA',nivel=4),[])
        self.fuente.aprobada=False; self.fuente.save()
        self.assertEqual(b.buscar_texto(consulta='division',asignatura='Matemática',ciclo='BASICA',nivel=4),[])

    def test_no_recupera_tablas_multinivel_aunque_el_encabezado_este_en_otro_fragmento(self):
        self.sincronizar()
        d=DocumentoCurricular.objects.get()
        FragmentoCurricular.objects.create(documento=d,numero=2,pagina=2,
            texto='NIVEL 1° BÁSICO NIVEL 2° BÁSICO NIVEL 3° BÁSICO')
        FragmentoCurricular.objects.create(documento=d,numero=3,pagina=2,
            texto='Division division multiplicacion multiplicacion: tablas de otros cursos.')
        resultados=b.buscar_texto(consulta='division',asignatura='Matemática',ciclo='BASICA',nivel=4)
        self.assertTrue(resultados); self.assertEqual({f['pagina'] for f in resultados},{1})
        self.assertEqual(d.fragmentos.count(),3)

    def test_paquete_restaurable_original_y_texto_sin_modelos_privados(self):
        self.sincronizar(); original=DocumentoCurricular.objects.get(); texto=original.fragmentos.get().texto
        paquete=paquetes.exportar()
        with zipfile.ZipFile(io.BytesIO(paquete)) as z:
            manifiesto=json.loads(z.read('manifiesto.json'))
            self.assertEqual(set(manifiesto),{'formato','creado','documentos'})
            self.assertIn('licencia',manifiesto['documentos'][0])
        original.delete()
        self.assertEqual(paquetes.importar(paquete),1)
        restaurado=DocumentoCurricular.objects.get()
        self.assertEqual(restaurado.sha256,b.huella(self.pdf)); self.assertEqual(restaurado.fragmentos.get().texto,texto)
        self.assertEqual(b.ruta_original(restaurado.sha256).read_bytes(),self.pdf)
        self.assertEqual(paquetes.importar(paquete),1); self.assertEqual(DocumentoCurricular.objects.count(),1)

    def test_paquete_manipulado_o_ruta_peligrosa_no_importa(self):
        self.sincronizar(); paquete=paquetes.exportar()
        for nombre,valor in [('../fuera.txt',b'x'), ('originales/'+b.huella(self.pdf)+'.pdf',b'corrupto')]:
            salida=io.BytesIO()
            with zipfile.ZipFile(io.BytesIO(paquete)) as origen, zipfile.ZipFile(salida,'w') as destino:
                for archivo in origen.namelist():
                    if archivo!=nombre: destino.writestr(archivo,origen.read(archivo))
                destino.writestr(nombre,valor)
            with self.assertRaises(ErrorIA): paquetes.importar(salida.getvalue())
        self.assertEqual(DocumentoCurricular.objects.count(),1)

    def test_exportar_no_incluye_documentos_ajenos_al_catalogo_aprobado(self):
        self.sincronizar()
        DocumentoCurricular.objects.create(titulo='Material reservado fuera de la biblioteca',
            asignatura='Matemática',ciclo='BASICA',nivel=4,sha256='a'*64)
        with zipfile.ZipFile(io.BytesIO(paquetes.exportar())) as z:
            indice=json.loads(z.read('manifiesto.json'))
        self.assertEqual(len(indice['documentos']),1)
        self.assertNotIn('Material reservado',json.dumps(indice))

    def test_vectores_qwen_reanudables_sin_gemini_y_compatibles_al_importar(self):
        self.sincronizar()
        with mock.patch('colegio.ia.rag.crear_embeddings',return_value=[[1.0]+[0.0]*767]) as crear:
            self.assertEqual(b.indexar_vectores('qwen',maximo=1),1)
            self.assertEqual(b.indexar_vectores('qwen',maximo=1),0)
        self.assertEqual(crear.call_args.kwargs['proveedor'],'qwen'); self.assertEqual(crear.call_count,1)
        paquete=paquetes.exportar(); DocumentoCurricular.objects.all().delete(); paquetes.importar(paquete)
        f=FragmentoCurricular.objects.get(); self.assertIsNone(f.embedding); self.assertIsNotNone(f.embedding_qwen)
        FragmentoCurricular.objects.update(embedding_qwen=None)
        paquetes.importar(paquete)
        self.assertIsNotNone(FragmentoCurricular.objects.get().embedding_qwen)
        DocumentoCurricular.objects.all().delete()
        with override_settings(QWEN_EMBEDDING_MODEL='otro-modelo'): paquetes.importar(paquete)
        self.assertIsNone(FragmentoCurricular.objects.get().embedding_qwen)

    def test_vectorial_explicito_no_oculta_indices_pendientes(self):
        self.sincronizar()
        with override_settings(BIBLIOTECA_BUSQUEDA='vectorial'), usar_proveedor('qwen'), self.assertRaises(ErrorIA):
            b.recuperar(consulta='division',asignatura='Matemática',ciclo='BASICA',nivel=4)

    def test_planificador_solo_fuentes_aprobadas_y_vencidas(self):
        from .tasks import actualizar_biblioteca
        with mock.patch.object(b,'sincronizar') as actualizar:
            actualizar_biblioteca(); actualizar.assert_called_once_with(self.fuente.pk)
            actualizar.reset_mock(); self.fuente.proxima_revision=timezone.now()+timedelta(days=6); self.fuente.save()
            actualizar_biblioteca(); actualizar.assert_not_called()


class BibliotecaFlujoTests(BibliotecaBase, AsistenteIATestBase):
    def setUp(self):
        super().setUp(); self.iniciar_biblioteca(); self.client.force_login(self.usuario_docente)

    def test_sesion_caducada_dirige_al_login_existente(self):
        self.client.logout()
        r=self.client.get(reverse('ia_biblioteca'))
        self.assertRedirects(r,reverse('login')+'?next='+reverse('ia_biblioteca'),fetch_redirect_response=False)

    def test_pagina_y_busqueda_solo_cargas_propias(self):
        self.sincronizar()
        respuesta=self.client.get(reverse('ia_biblioteca'),{'q':'division','carga':self.carga.pk})
        self.assertContains(respuesta,'página PDF 1'); self.assertContains(respuesta,'sin consumo de embeddings')
        ajena=self.client.get(reverse('ia_biblioteca'),{'q':'division','carga':self.carga_ajena.pk})
        self.assertIsNone(ajena.context['carga']); self.assertEqual(ajena.context['resultados'],[])

    def test_post_sync_no_api_y_descarga_limitada_al_propietario(self):
        with mock.patch.object(b,'localizar_pdf',return_value=self.fuente.descarga_url), \
             mock.patch.object(b,'descargar',return_value=(self.pdf,self.fuente.descarga_url)), \
             mock.patch('colegio.ia.rag.crear_embeddings') as api:
            respuesta=self.client.post(reverse('ia_biblioteca_actualizar',args=[self.fuente.pk]),{'idempotencia':uuid.uuid4()})
        self.assertEqual(respuesta.status_code,302); api.assert_not_called()
        trabajo=TrabajoIA.objects.get(); self.assertEqual(trabajo.estado,'completado'); self.assertFalse(RegistroIA.objects.exists())
        token=uuid.uuid4()
        self.client.post(reverse('ia_biblioteca_exportar'),{'idempotencia':token})
        self.client.post(reverse('ia_biblioteca_exportar'),{'idempotencia':token})
        exportacion=TrabajoIA.objects.get(operacion='biblioteca_export')
        self.assertEqual(exportacion.estado,'completado')
        descarga=reverse('ia_trabajo_descargar',args=[exportacion.pk])
        r=self.client.get(descarga); self.assertEqual(r['Content-Type'],'application/zip')
        self.assertTrue(b''.join(r.streaming_content).startswith(b'PK'))
        self.client.force_login(self.usuario_otro_docente)
        self.assertEqual(self.client.get(descarga).status_code,404)
        self.assertEqual(self.client.get(reverse('ia_trabajo_estado',args=[exportacion.pk])).status_code,404)

    def test_actualizar_requiere_post_docente_y_catalogo_aprobado(self):
        url=reverse('ia_biblioteca_actualizar',args=[self.fuente.pk])
        self.assertEqual(self.client.get(url).status_code,405)
        self.fuente.aprobada=False; self.fuente.save()
        self.assertEqual(self.client.post(url).status_code,404)
        self.client.force_login(self.usuario_alumno)
        self.assertEqual(self.client.get(reverse('ia_biblioteca')).status_code,302)

    def test_los_cuatro_modulos_consultan_el_mismo_corpus(self):
        from . import views_ia
        from .ia import dominio
        from .ia.tutor.rag_service import recuperar_contexto
        self.sincronizar()
        datos={'carga':self.carga,'objetivo':'Multiplicacion y division','tema':'division','cantidad':3,
               'dificultad':'media','actividad':'division','criterios':3,'niveles':4,'tipo':'guia'}
        contexto=dominio.contexto_carga(self.carga)
        with usar_proveedor('qwen'), mock.patch('colegio.ia.rag.crear_embeddings') as api:
            for modulo,generador in [('prueba',views_ia._generar_prueba_con_rag),
                                     ('rubrica',views_ia._generar_rubrica_con_rag), ('material',views_ia._generar_material_con_rag)]:
                with mock.patch.object(views_ia.asistentes,'crear_'+modulo) as modelo:
                    generador(contexto,datos)
                self.assertEqual(modelo.call_args.kwargs['fragmentos'][0]['pagina'],1)
            tutor=recuperar_contexto('division',contexto=dominio.contexto_tutor(self.asignatura))
        self.assertEqual(tutor[0]['url'],self.fuente.descarga_url); api.assert_not_called()
