from copy import deepcopy
import uuid

from django.urls import reverse

from .models import InstrumentoIA, TrabajoIA
from .tests import AsistenteIATestBase


class NavegacionIATests(AsistenteIATestBase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.usuario_docente)

    def material(self, titulo='Material propio', ajeno=False):
        contenido = {'titulo': titulo, 'contenido': '# Explicación\n\nUn **ejemplo**. Comparar 3 < 5 & 8 > 4.\n\n<img src=x onerror="alert(1)">',
            'ejercicios': '1. Calcula 2 + 3.', 'solucionario': '5.',
            'version_estructura': 2, 'separacion_revisada': False}
        return InstrumentoIA.objects.create(docente=self.usuario_otro_docente.docente if ajeno else self.docente,
            carga=self.carga_ajena if ajeno else self.carga, tipo='MATERIAL', titulo=titulo,
            contenido=contenido, contenido_ia=deepcopy(contenido), estado='BORRADOR')

    def test_portada_ofrece_submenu_sin_cargar_los_dos_paneles(self):
        pagina = self.client.get(reverse('asistente_docente'))
        self.assertContains(pagina, reverse('ia_documentos'))
        self.assertContains(pagina, reverse('ia_operaciones'))
        self.assertNotContains(pagina, 'class="ia-trabajos-lista"')
        self.assertNotContains(pagina, 'class="ia-tabla"')

    def test_documentos_paginados_excluyen_los_de_otro_docente(self):
        self.material('Material ajeno', ajeno=True)
        for numero in range(16):
            self.material(f'Material propio {numero}')
        pagina = self.client.get(reverse('ia_documentos'))
        self.assertEqual(pagina.context['pagina'].paginator.count, 16)
        self.assertEqual(len(pagina.context['pagina']), 15)
        self.assertNotContains(pagina, 'Material ajeno')
        segunda = self.client.get(reverse('ia_documentos'), {'pagina': 2})
        self.assertEqual(len(segunda.context['pagina']), 1)
        self.assertNotContains(segunda, 'Material ajeno')

    def test_operaciones_excluyen_las_de_otro_docente(self):
        for usuario, operacion in [(self.usuario_docente, 'material'), (self.usuario_otro_docente, 'revision_ajena')]:
            TrabajoIA.objects.create(usuario=usuario, sesion='prueba', idempotencia=uuid.uuid4(),
                huella='a'*64, conexion_huella='b'*64, operacion=operacion, proveedor='simulado', modelo='simulado')
        pagina = self.client.get(reverse('ia_operaciones'))
        self.assertEqual(pagina.context['pagina'].paginator.count, 1)
        self.assertNotContains(pagina, 'Revision_Ajena')

    def test_listados_requieren_docente_autenticado(self):
        self.client.force_login(self.usuario_alumno)
        for ruta in ('ia_documentos', 'ia_operaciones'):
            self.assertEqual(self.client.get(reverse(ruta)).status_code, 302)
        self.client.logout()
        for ruta in ('ia_documentos', 'ia_operaciones'):
            self.assertIn('/login/', self.client.get(reverse(ruta)).url)

    def test_editor_carga_html_seguro_y_conserva_el_original_al_guardar(self):
        instrumento = self.material()
        original = deepcopy(instrumento.contenido_ia)
        pagina = self.client.get(reverse('ia_instrumento', args=[instrumento.pk]))
        self.assertContains(pagina, 'data-editor-material')
        self.assertContains(pagina, '<strong>ejemplo</strong>', html=True)
        self.assertContains(pagina, 'name="contenido"')
        self.assertNotContains(pagina, '&amp;lt;')
        self.assertNotContains(pagina, '<img src=x')
        self.client.post(reverse('ia_instrumento', args=[instrumento.pk]), {**original, 'separacion_revisada': '', 'accion': 'guardar'})
        instrumento.refresh_from_db()
        self.assertEqual(instrumento.contenido_ia, original)
        self.assertEqual(instrumento.contenido['contenido'], original['contenido'])
        self.assertEqual(instrumento.contenido['solucionario'], original['solucionario'])
