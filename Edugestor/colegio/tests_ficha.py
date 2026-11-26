"""Ficha visual (infografía de una página) del material de estudio."""
from django.test import SimpleTestCase
from django.urls import reverse

from .ia import asistentes
from .ia.ficha import ICONOS, validar_ficha
from .models import InstrumentoIA
from .tests import AsistenteIATestBase

FICHA = {
    "titulo": "Técnicas de estudio", "subtitulo": "Guía para el estudio",
    "idea": {"pregunta": "¿Qué son?", "respuesta": "Métodos que mejoran tu rendimiento."},
    "tarjetas": [{"titulo": f"Tarjeta {i}", "texto": "Una frase corta.", "icono": "libro"} for i in range(1, 7)],
    "recuerda": "Estudia un poco cada día.",
}


class ValidarFichaTests(SimpleTestCase):
    def test_normaliza_textos_e_iconos(self):
        ficha = validar_ficha({**FICHA, "titulo": "  Técnicas   de\nestudio ",
                               "tarjetas": FICHA["tarjetas"][:3] + [
                                   {"titulo": "Haz mapas", "texto": "x" * 300, "icono": "<svg onload=1>"},
                                   {"titulo": "Grábalo", "icono": "Lápiz"}]})

        self.assertEqual(ficha["titulo"], "Técnicas de estudio")
        self.assertEqual(ficha["tarjetas"][3]["icono"], "idea")
        self.assertEqual(ficha["tarjetas"][4]["icono"], "lapiz")
        self.assertLessEqual(len(ficha["tarjetas"][3]["texto"]), 110)
        self.assertTrue(all(t["icono"] in ICONOS for t in ficha["tarjetas"]))

    def test_rechaza_fichas_incompletas_o_invalidas(self):
        self.assertIsNone(validar_ficha(None))
        self.assertIsNone(validar_ficha("<div>html</div>"))
        self.assertIsNone(validar_ficha({**FICHA, "tarjetas": FICHA["tarjetas"][:3]}))
        self.assertIsNone(validar_ficha({**FICHA, "titulo": ""}))
        sin_titulos = [{"titulo": "", "texto": "x"}] * 6
        self.assertIsNone(validar_ficha({**FICHA, "tarjetas": sin_titulos}))

    def test_limita_a_ocho_tarjetas(self):
        muchas = [{"titulo": f"T{i}", "icono": "check"} for i in range(12)]
        self.assertEqual(len(validar_ficha({**FICHA, "tarjetas": muchas})["tarjetas"]), 8)

    def test_material_sin_ficha_valida_se_conserva_y_queda_pendiente(self):
        material = asistentes.validar_material({"titulo": "M", "contenido": "Texto", "ejercicios": "",
                                                "solucionario": "", "ficha": {"titulo": "Solo título"}})
        self.assertNotIn("ficha", material)
        self.assertTrue(material["ficha_pendiente"])

    def test_textos_de_incluye_la_ficha(self):
        textos = asistentes.textos_de("MATERIAL", {"titulo": "M", "contenido": "", "ficha": FICHA})
        self.assertIn("Técnicas de estudio", textos)
        self.assertIn("Tarjeta 3", textos)


class FichaMaterialTests(AsistenteIATestBase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.usuario_docente)

    def crear(self, tipo="ficha"):
        self.client.post(reverse("ia_crear_material"), {
            "carga": self.carga.pk, "tema": "multiplicación", "tipo": tipo, "objetivo": "OA 3",
            "contexto_curricular": "personalizado",
        })
        return InstrumentoIA.objects.filter(tipo=InstrumentoIA.TIPO_MATERIAL).latest("fecha_creacion")

    def post_material(self, material, accion="guardar", **cambios):
        contenido = material.contenido
        datos = {"accion": accion, "titulo": contenido["titulo"], "contenido": contenido["contenido"],
                 "ejercicios": contenido["ejercicios"], "solucionario": contenido["solucionario"],
                 "separacion_revisada": "on"}
        ficha = contenido.get("ficha")
        if ficha:
            datos.update(ficha_presente="1", ficha_titulo=ficha["titulo"], ficha_subtitulo=ficha["subtitulo"],
                         ficha_pregunta=ficha["idea"]["pregunta"], ficha_respuesta=ficha["idea"]["respuesta"],
                         ficha_recuerda=ficha["recuerda"])
            for i, tarjeta in enumerate(ficha["tarjetas"]):
                datos.update({f"ficha_t{i}_titulo": tarjeta["titulo"], f"ficha_t{i}_texto": tarjeta["texto"],
                              f"ficha_t{i}_icono": tarjeta["icono"]})
        datos.update(cambios)
        return self.client.post(reverse("ia_instrumento", args=[material.pk]), datos)

    def test_el_tipo_ficha_es_el_predeterminado(self):
        formulario = self.client.get(reverse("ia_crear_material")).context["form"]
        self.assertEqual(list(formulario.fields["tipo"].choices)[0][0], "ficha")

    def test_crear_material_guarda_la_ficha(self):
        material = self.crear("ficha")
        self.assertEqual(material.contenido["ficha"]["subtitulo"], "Guía para el estudio")
        self.assertEqual(len(material.contenido["ficha"]["tarjetas"]), 6)

    def test_otros_tipos_no_generan_portada(self):
        # La portada solo corresponde a la ficha; el docente puede crearla a mano si la quiere.
        material = self.crear("guia")
        self.assertNotIn("ficha", material.contenido)
        self.assertNotIn("ficha_pendiente", material.contenido)
        pagina = self.client.get(reverse("ia_instrumento", args=[material.pk]))
        self.assertContains(pagina, "Crear ficha visual")

    def test_editor_muestra_y_modifica_la_ficha(self):
        material = self.crear()
        pagina = self.client.get(reverse("ia_instrumento", args=[material.pk]))
        self.assertContains(pagina, 'name="ficha_t5_icono"')
        self.assertContains(pagina, "Agregar tarjeta")

        self.post_material(material, ficha_titulo="Multiplicar sin miedo", ficha_t0_icono="estrella",
                           ficha_t1_eliminar="on", ficha_t9_titulo="Practica cada día", ficha_t9_texto="Diez minutos.",
                           ficha_t9_icono="reloj")

        material.refresh_from_db()
        ficha = material.contenido["ficha"]
        self.assertEqual(ficha["titulo"], "Multiplicar sin miedo")
        self.assertEqual(ficha["tarjetas"][0]["icono"], "estrella")
        self.assertEqual(len(ficha["tarjetas"]), 6)
        self.assertEqual(ficha["tarjetas"][-1]["titulo"], "Practica cada día")
        self.assertNotIn("Descompón los números", [t["titulo"] for t in ficha["tarjetas"]])

    def test_ficha_con_pocas_tarjetas_no_se_guarda(self):
        material = self.crear()
        eliminar = {f"ficha_t{i}_eliminar": "on" for i in range(3)}

        respuesta = self.post_material(material, **eliminar)

        self.assertContains(respuesta, "al menos 4 tarjetas")
        material.refresh_from_db()
        self.assertEqual(len(material.contenido["ficha"]["tarjetas"]), 6)

    def test_quitar_y_volver_a_crear_la_ficha(self):
        material = self.crear()
        self.post_material(material, ficha_quitar="on")
        material.refresh_from_db()
        self.assertNotIn("ficha", material.contenido)
        pagina = self.client.get(reverse("ia_instrumento", args=[material.pk]))
        self.assertContains(pagina, "Crear ficha visual")

    def test_guardar_sin_la_seccion_de_ficha_la_conserva(self):
        material = self.crear()
        contenido = material.contenido
        self.client.post(reverse("ia_instrumento", args=[material.pk]), {
            "accion": "guardar", "titulo": contenido["titulo"], "contenido": contenido["contenido"],
            "ejercicios": contenido["ejercicios"], "solucionario": contenido["solucionario"]})
        material.refresh_from_db()
        self.assertEqual(material.contenido["ficha"], contenido["ficha"])

    def test_ficha_en_versiones_del_estudiante_y_docente(self):
        material = self.crear("ficha")
        self.post_material(material, accion="aprobar")
        material.refresh_from_db()
        self.assertEqual(material.estado, InstrumentoIA.ESTADO_APROBADO)

        estudiante = self.client.get(reverse("ia_imprimir", args=[material.pk, "estudiante"]))
        docente = self.client.get(reverse("ia_imprimir", args=[material.pk, "docente"]))
        aprobado = self.client.get(reverse("ia_instrumento", args=[material.pk]))

        for respuesta in (estudiante, docente, aprobado):
            self.assertContains(respuesta, 'class="ficha"')
            self.assertContains(respuesta, "Descompón los números")
            self.assertContains(respuesta, 'class="ficha-icono"')
        self.assertContains(estudiante, 'class="despues-ficha"')
        self.assertNotContains(estudiante, "(20 × 3) + (4 × 3)")
        self.assertContains(docente, "(20 × 3) + (4 × 3)")

    def test_material_antiguo_sin_ficha_se_ve_como_antes(self):
        material = InstrumentoIA.objects.create(
            docente=self.docente, carga=self.carga, tipo="MATERIAL", titulo="Antiguo", estado="APROBADO",
            contenido_ia={}, contenido={"titulo": "Antiguo", "contenido": "## Hola", "ejercicios": "1. Uno",
                                         "solucionario": "1", "version_estructura": 2, "separacion_revisada": True})
        respuesta = self.client.get(reverse("ia_imprimir", args=[material.pk, "estudiante"]))
        self.assertNotContains(respuesta, 'class="ficha"')
        self.assertContains(respuesta, "Hola")

    def test_copiar_conserva_la_ficha(self):
        material = self.crear()
        self.post_material(material, accion="aprobar")

        self.client.post(reverse("ia_copiar", args=[material.pk]))

        copia = InstrumentoIA.objects.exclude(pk=material.pk).get(tipo="MATERIAL")
        self.assertEqual(copia.contenido["ficha"], InstrumentoIA.objects.get(pk=material.pk).contenido["ficha"])


class RecuadroRecuerdaTests(SimpleTestCase):
    def test_cita_markdown_se_muestra_como_recuadro_sin_html_inyectado(self):
        from .templatetags.ia_extras import markdown_seguro
        html = str(markdown_seguro("> **Recuerda:** descompón <script>alert(1)</script>\n\n2 > 1"))
        self.assertIn("<blockquote>", html)
        self.assertIn("<strong>Recuerda:</strong>", html)
        self.assertNotIn("<script>", html)
        self.assertIn("2 &gt; 1", html)
