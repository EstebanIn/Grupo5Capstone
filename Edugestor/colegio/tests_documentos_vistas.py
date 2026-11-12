from copy import deepcopy
from django.test import SimpleTestCase, RequestFactory, override_settings
from django.urls import reverse
from .tests import AsistenteIATestBase
from .models import InstrumentoIA, TrabajoIA



class DocumentosVistaTests(AsistenteIATestBase):
    def setUp(self):
        super().setUp();self.client.force_login(self.usuario_docente)

    def test_material_legacy_aprobado_se_copia_sin_mutarlo(self):
        original=InstrumentoIA.objects.create(docente=self.docente,carga=self.carga,tipo='MATERIAL',
            titulo='Antiguo',contenido={'titulo':'Antiguo','texto':'Ejercicio y respuesta antigua'},contenido_ia={'texto':'Original'},estado='APROBADO')
        antes=deepcopy(original.contenido)
        self.assertEqual(self.client.post(reverse('ia_exportar',args=[original.pk]),{'version':'estudiante'}).status_code,400)
        self.client.post(reverse('ia_copiar',args=[original.pk]))
        original.refresh_from_db();self.assertEqual(original.contenido,antes)
        copia=InstrumentoIA.objects.exclude(pk=original.pk).get()
        self.assertEqual(copia.estado,'BORRADOR');self.assertFalse(copia.contenido['separacion_revisada'])
        self.client.post(reverse('ia_copiar',args=[original.pk]))
        self.assertEqual(InstrumentoIA.objects.count(),2)
        self.assertEqual(self.client.get(reverse('ia_copiar',args=[original.pk])).status_code,405)

    def test_exportar_requiere_post_aprobacion_y_propiedad(self):
        self.crear_prueba();i=InstrumentoIA.objects.get()
        self.assertEqual(self.client.post(reverse('ia_exportar',args=[i.pk])).status_code,404)
        self.post_prueba(i,'aprobar')
        self.assertEqual(self.client.get(reverse('ia_exportar',args=[i.pk])).status_code,405)
        self.client.force_login(self.usuario_otro_docente)
        self.assertEqual(self.client.post(reverse('ia_exportar',args=[i.pk])).status_code,404)
        self.assertEqual(self.client.get(reverse('ia_imprimir',args=[i.pk,'docente'])).status_code,404)

    def test_descarga_pdf_privada_y_pauta_fuera_del_html_estudiante(self):
        self.crear_prueba();i=InstrumentoIA.objects.get();self.post_prueba(i,'aprobar')
        respuesta=self.client.post(reverse('ia_exportar',args=[i.pk]),{'version':'estudiante'})
        t=TrabajoIA.objects.get(operacion='exportar')
        self.assertEqual(t.estado,'completado',t.mensaje)
        descarga=self.client.get(reverse('ia_trabajo_descargar',args=[t.pk]))
        self.assertEqual(descarga.status_code,200)
        self.assertIn('no-store',descarga['Cache-Control'])
        self.assertTrue(b''.join(descarga.streaming_content).startswith(b'%PDF'))
        html=self.client.get(reverse('ia_imprimir',args=[i.pk,'estudiante']))
        self.assertNotContains(html,'Explicación de ejemplo')
        from .ia.trabajos import ruta_privada
        ruta_privada(t.archivo).unlink(missing_ok=True)
