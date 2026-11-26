"""Cobertura, propuestas de fuentes (docente propone, admin aprueba) y vectores desde la interfaz."""
import uuid
from unittest import mock

from django.test import SimpleTestCase
from django.urls import reverse

from .ia import biblioteca as b, biblioteca_gestion as gestion
from .ia.proveedor import ErrorIA
from .models import (Asignatura, CargaAcademica, DocumentoCurricular, FragmentoCurricular, FuenteBiblioteca,
                     TrabajoIA, Usuario)
from .tests import AsistenteIATestBase
from .tests_biblioteca import BibliotecaBase

FICHA = 'https://www.curriculumnacional.cl/recursos/programa-estudio-historia-4-basico'


class GestionBibliotecaTests(BibliotecaBase, AsistenteIATestBase):
    def setUp(self):
        super().setUp()
        self.iniciar_biblioteca()
        self.historia = Asignatura.objects.create(nombre_asignatura='Historia, Geografía y Ciencias Sociales',
                                                  curso=self.curso)
        self.carga_historia = CargaAcademica.objects.create(curso=self.curso, asignatura=self.historia,
                                                            periodo=self.periodo, docente=self.docente)
        self.admin = Usuario.objects.create_user(username='admin_bib', password='x', rut='11.111.111-1',
                                                 tipo_usuario='ADMIN')
        self.client.force_login(self.usuario_docente)

    def fila(self, respuesta, asignatura):
        return next(f for f in respuesta.context['cobertura'] if f['asignatura'] == asignatura)

    def proponer(self, **datos):
        return self.client.post(reverse('ia_biblioteca_proponer'),
                                {'carga': self.carga_historia.pk, 'ficha_url': FICHA, **datos})

    # ---------- Cobertura ----------
    def test_cobertura_muestra_estado_de_cada_curso(self):
        pagina = self.client.get(reverse('ia_biblioteca'))
        self.assertEqual(self.fila(pagina, 'Matemática')['estado'], 'aprobada')
        historia = self.fila(pagina, 'Historia, Geografía y Ciencias Sociales')
        self.assertEqual(historia['estado'], 'sin_fuente')
        self.assertContains(pagina, f'?proponer={self.carga_historia.pk}#proponer')
        self.assertContains(pagina, 'Indexar ahora')

        self.sincronizar()
        pagina = self.client.get(reverse('ia_biblioteca'))
        matematica = self.fila(pagina, 'Matemática')
        self.assertEqual((matematica['estado'], matematica['origen']), ('lista', 'biblioteca'))

    def test_cobertura_reconoce_el_corpus_anterior(self):
        documento = DocumentoCurricular.objects.create(titulo='Corpus previo', asignatura='Historia, Geografía y Ciencias Sociales',
                                                       ciclo='BASICA', nivel=4, sha256='a' * 64)
        FragmentoCurricular.objects.create(documento=documento, numero=1, texto='Pueblos originarios')

        fila = gestion.cobertura(asignatura='Historia, Geografía y Ciencias Sociales', ciclo='BASICA', nivel=4)

        self.assertEqual((fila['estado'], fila['origen'], fila['qwen']), ('lista', 'anterior', False))

    # ---------- Propuestas del docente ----------
    def test_docente_propone_una_fuente_oficial(self):
        respuesta = self.proponer(titulo='Programa Historia 4° básico')

        fuente = FuenteBiblioteca.objects.get(ficha_url=FICHA)
        self.assertRedirects(respuesta, reverse('ia_biblioteca') + '#mis-propuestas', fetch_redirect_response=False)
        self.assertEqual((fuente.aprobada, fuente.estado, fuente.propuesta_por), (False, 'propuesta', self.usuario_docente))
        self.assertEqual((fuente.asignatura, fuente.ciclo, fuente.nivel),
                         ('Historia, Geografía y Ciencias Sociales', 'BASICA', 4))
        pagina = self.client.get(reverse('ia_biblioteca'))
        self.assertEqual(self.fila(pagina, 'Historia, Geografía y Ciencias Sociales')['estado'], 'propuesta')
        self.assertContains(pagina, 'Mis propuestas')
        # Una propuesta no se puede indexar hasta que el administrador la apruebe.
        self.assertEqual(self.client.post(reverse('ia_biblioteca_actualizar', args=[fuente.pk])).status_code, 404)

    def test_rechaza_dominios_no_oficiales_duplicados_y_cursos_ajenos(self):
        for url in ('https://evil.test/programa', 'http://www.curriculumnacional.cl/recursos/x',
                    'https://curriculumnacional.cl.evil.test/x'):
            respuesta = self.proponer(ficha_url=url)
            self.assertContains(self.client.get(respuesta.url), 'dominio curricular autorizado')
        self.proponer(descarga_url='https://www.curriculumnacional.cl/614/no-es-pdf.html')
        self.assertFalse(FuenteBiblioteca.objects.filter(ficha_url=FICHA).exists())

        self.proponer()
        respuesta = self.proponer()
        self.assertContains(self.client.get(respuesta.url), 'ya está en el catálogo')
        self.client.post(reverse('ia_biblioteca_proponer'), {'carga': self.carga_ajena.pk,
                                                             'ficha_url': FICHA + '-otro'})
        self.assertEqual(FuenteBiblioteca.objects.filter(propuesta_por=self.usuario_docente).count(), 1)

    def test_limite_de_propuestas_pendientes(self):
        for i in range(gestion.MAX_PROPUESTAS_PENDIENTES):
            self.proponer(ficha_url=f'{FICHA}-{i}')
        respuesta = self.proponer(ficha_url=f'{FICHA}-extra')
        self.assertContains(self.client.get(respuesta.url), 'propuestas pendientes')

    # ---------- Revisión del administrador ----------
    def test_solo_el_administrador_revisa(self):
        self.proponer()
        fuente = FuenteBiblioteca.objects.get(ficha_url=FICHA)
        self.assertEqual(self.client.get(reverse('panel_admin_biblioteca')).status_code, 302)
        self.client.post(reverse('panel_admin_biblioteca_revisar', args=[fuente.pk]), {'accion': 'aprobar'})
        fuente.refresh_from_db()
        self.assertFalse(fuente.aprobada)

        self.client.force_login(self.admin)
        pagina = self.client.get(reverse('panel_admin_biblioteca'))
        self.assertContains(pagina, 'Propuestas pendientes (1)')
        self.assertContains(pagina, FICHA)

    def test_admin_aprueba_y_encola_la_indexacion(self):
        self.proponer()
        fuente = FuenteBiblioteca.objects.get(ficha_url=FICHA)
        self.client.force_login(self.admin)
        # El cliente de AsistenteIATestBase ya ejecuta los callbacks on_commit.
        with mock.patch('colegio.tasks.sincronizar_fuente.apply_async') as encolar:
            self.client.post(reverse('panel_admin_biblioteca_revisar', args=[fuente.pk]),
                             {'accion': 'aprobar', 'titulo': 'Programa de Estudio Historia · 4° básico',
                              'descarga_url': 'https://www.curriculumnacional.cl/614/articles-20000_programa.pdf'})

        fuente.refresh_from_db()
        self.assertTrue(fuente.aprobada)
        self.assertEqual((fuente.estado, fuente.revisada_por), ('pendiente', self.admin))
        self.assertEqual(fuente.titulo, 'Programa de Estudio Historia · 4° básico')
        encolar.assert_called_once_with(args=[fuente.pk], retry=False)

    def test_admin_rechaza_con_motivo_visible_para_el_docente(self):
        self.proponer()
        fuente = FuenteBiblioteca.objects.get(ficha_url=FICHA)
        self.client.force_login(self.admin)
        url = reverse('panel_admin_biblioteca_revisar', args=[fuente.pk])
        self.client.post(url, {'accion': 'rechazar', 'motivo': ''})
        fuente.refresh_from_db()
        self.assertEqual(fuente.estado, 'propuesta')

        self.client.post(url, {'accion': 'rechazar', 'motivo': 'Es una guía de otro nivel.'})
        fuente.refresh_from_db()
        self.assertEqual(fuente.estado, 'rechazada')
        self.client.force_login(self.usuario_docente)
        pagina = self.client.get(reverse('ia_biblioteca'))
        self.assertContains(pagina, 'Es una guía de otro nivel.')
        self.assertEqual(self.fila(pagina, 'Historia, Geografía y Ciencias Sociales')['estado'], 'sin_fuente')
        # Rechazada, se puede volver a proponer la misma ficha.
        self.proponer()
        self.assertEqual(FuenteBiblioteca.objects.filter(ficha_url=FICHA).count(), 2)

    def test_tarea_de_aprobacion_indexa_buscando_el_pdf_en_la_ficha(self):
        from .tasks import sincronizar_fuente
        self.proponer()
        fuente = FuenteBiblioteca.objects.get(ficha_url=FICHA)
        gestion.aprobar_fuente(fuente, self.admin)
        html = b'<a href="/614/articles-20000_programa.pdf">Descargar</a>'
        pdf_url = 'https://www.curriculumnacional.cl/614/articles-20000_programa.pdf'

        def descargar(url, **kwargs):
            return (html, FICHA) if url == FICHA else (self.pdf, url)
        with mock.patch.object(b, 'descargar', side_effect=descargar) as descarga:
            sincronizar_fuente(fuente.pk)

        fuente.refresh_from_db()
        self.assertEqual(fuente.estado, 'disponible')
        self.assertEqual(descarga.call_args_list[-1].args[0], pdf_url)
        self.assertEqual(gestion.cobertura(asignatura='Historia, Geografía y Ciencias Sociales',
                                           ciclo='BASICA', nivel=4)['estado'], 'lista')

    # ---------- Vectores ----------
    def test_vectores_requieren_proveedor_real_y_avanzan_por_lotes(self):
        self.sincronizar()
        respuesta = self.client.post(reverse('ia_biblioteca_vectores'), {'maximo': 25})
        self.assertContains(self.client.get(respuesta.url), 'Selecciona Qwen o Gemini')

        with mock.patch('colegio.ia.rag.crear_embeddings', side_effect=lambda textos, **k: [[1.0] + [0.0] * 767] * len(textos)):
            self.client.post(reverse('ia_biblioteca_vectores'),
                             {'proveedor': 'qwen', 'maximo': 25, 'idempotencia': uuid.uuid4()})
        trabajo = TrabajoIA.objects.get(operacion='biblioteca_vectores')
        self.assertEqual(trabajo.estado, 'completado', trabajo.mensaje)
        qwen = next(v for v in gestion.estado_vectores() if v['proveedor'] == 'qwen')
        self.assertEqual(qwen['listos'], qwen['total'])

    def test_error_sin_fuentes_lleva_a_la_biblioteca(self):
        self.client.post(reverse('ia_crear_prueba'), {'proveedor': 'qwen', 'carga': self.carga_historia.pk,
                                                      'tema': 'Pueblos', 'cantidad': 3, 'dificultad': 'media'})
        trabajo = TrabajoIA.objects.get(operacion='prueba')
        self.assertIn('Biblioteca curricular', trabajo.mensaje)
        pagina = self.client.get(reverse('ia_trabajo', args=[trabajo.pk]))
        import re
        enlace = re.search(r'<a id="trabajo-biblioteca"[^>]*>', pagina.content.decode()).group(0)
        self.assertIn(reverse('ia_biblioteca') + '#cobertura', enlace)
        self.assertNotIn('hidden', enlace)


class NombreNivelTests(SimpleTestCase):
    def test_nombres(self):
        self.assertEqual(gestion.nombre_nivel('BASICA', 4), '4° básico')
        self.assertEqual(gestion.nombre_nivel('MEDIA', 2), '2° medio')
        self.assertEqual(gestion.nombre_nivel('KINDER', 2), 'Kínder')
