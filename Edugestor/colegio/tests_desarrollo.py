"""
Preguntas de desarrollo en las pruebas del Asistente IA: el alumno escribe su
desarrollo (o justificación), la fórmula (o concepto clave) y el resultado; la
lectura con IA transcribe los tres recuadros y sugiere un puntaje por criterio
que el docente confirma.

Con el proveedor simulado, una prueba con cantidad=3 y cantidad_desarrollo=2 tiene
pauta de selección B, C, D (preguntas 1 a 3) y dos preguntas de desarrollo (4 y 5)
de 4 puntos cada una (desarrollo 2, fórmula 1, resultado 1). La lectura simulada
marca B y C, deja la 3 en blanco y transcribe los tres recuadros de cada desarrollo.
"""
from unittest import mock

from django.apps import apps
from django.test import SimpleTestCase
from django.urls import reverse

from .ia import asistentes
from .ia.documentos import contexto_documento
from .ia.proveedor import ErrorIA
from .models import CorreccionPrueba, InstrumentoIA
from .tests import AsistenteIATestBase, hoja

DESARROLLO = {
    "tipo": "desarrollo", "enunciado": "Calcula el área de un rectángulo de 4 cm por 6 cm.",
    "formula": "A = base × altura", "desarrollo_esperado": "4 × 6 = 24", "resultado": "24 cm²",
    "criterios": [
        {"clave": "desarrollo", "nombre": "Desarrollo", "puntaje_maximo": 2, "descriptor": "Pasos"},
        {"clave": "formula", "nombre": "Fórmula", "puntaje_maximo": 1, "descriptor": ""},
        {"clave": "resultado", "nombre": "Resultado", "puntaje_maximo": 1, "descriptor": ""},
    ],
}
SELECCION = {"enunciado": "¿Cuánto es 2 + 2?", "alternativas": ["3", "4", "5", "6"], "correcta": 1}


class ReglasDesarrolloTests(SimpleTestCase):
    def test_componentes_segun_la_asignatura(self):
        calculo = [c["nombre"] for c in asistentes.componentes_desarrollo("Matemática")]
        humanista = [c["nombre"] for c in asistentes.componentes_desarrollo("Historia, Geografía y Ciencias Sociales")]

        self.assertEqual(calculo, ["Desarrollo del cálculo", "Fórmula utilizada", "Resultado"])
        self.assertEqual(humanista, ["Desarrollo / justificación", "Concepto o evidencia clave", "Conclusión"])
        self.assertTrue(asistentes.es_asignatura_de_calculo("Ciencias Naturales"))
        self.assertTrue(asistentes.es_asignatura_de_calculo("Física"))
        self.assertFalse(asistentes.es_asignatura_de_calculo("Lenguaje y Comunicación"))

    def test_valida_una_prueba_mixta_y_calcula_el_puntaje(self):
        prueba = asistentes.validar_prueba({"titulo": "Mixta", "preguntas": [SELECCION, DESARROLLO]})

        self.assertEqual([p["tipo"] for p in prueba["preguntas"]], ["seleccion", "desarrollo"])
        self.assertEqual(prueba["preguntas"][1]["puntaje"], 4)
        self.assertEqual(asistentes.puntaje_total_prueba(prueba), 5)

    def test_rechaza_desarrollo_sin_criterios_o_con_puntaje_invalido(self):
        with self.assertRaises(ErrorIA):
            asistentes.validar_prueba({"preguntas": [{**DESARROLLO, "criterios": []}]})
        criterio_invalido = [{**DESARROLLO["criterios"][0], "puntaje_maximo": 0}]
        with self.assertRaises(ErrorIA):
            asistentes.validar_prueba({"preguntas": [{**DESARROLLO, "criterios": criterio_invalido}]})
        repetido = [DESARROLLO["criterios"][0], DESARROLLO["criterios"][0]]
        with self.assertRaises(ErrorIA):
            asistentes.validar_prueba({"preguntas": [{**DESARROLLO, "criterios": repetido}]})

    def test_corrige_por_puntaje_con_desarrollo_parcial(self):
        prueba = asistentes.validar_prueba({"preguntas": [SELECCION, DESARROLLO]})

        resultado = asistentes.corregir_respuestas(prueba, [1, {"desarrollo": 1.5, "formula": 1, "resultado": 0}])

        self.assertEqual((resultado["puntaje_obtenido"], resultado["puntaje_maximo"]), (3.5, 5))
        self.assertEqual(resultado["detalle"][1]["estado"], "parcial")
        self.assertEqual(resultado["detalle"][1]["puntajes"], {"desarrollo": 1.5, "formula": 1, "resultado": 0})
        self.assertEqual(resultado["nota"], asistentes.nota_chilena(3.5, 5))

    def test_desarrollo_sin_puntaje_queda_omitido_y_se_acotan_los_valores(self):
        prueba = asistentes.validar_prueba({"preguntas": [DESARROLLO, DESARROLLO]})

        resultado = asistentes.corregir_respuestas(prueba, [
            {"desarrollo": None, "formula": None, "resultado": None},
            {"desarrollo": 9, "formula": -3, "resultado": 0.74},
        ])

        self.assertEqual(resultado["detalle"][0]["estado"], "omitida")
        self.assertEqual(resultado["detalle"][1]["puntajes"], {"desarrollo": 2, "formula": 0, "resultado": 0.5})

    def test_seleccion_multiple_se_corrige_igual_que_antes(self):
        prueba = asistentes.validar_prueba({"preguntas": [SELECCION] * 5})

        resultado = asistentes.corregir_respuestas(prueba, [1, 1, 1, 1, None])

        self.assertEqual((resultado["correctas"], resultado["total"]), (4, 5))
        self.assertEqual(resultado["nota"], 5.5)
        self.assertEqual(resultado["puntaje_obtenido"], 4)

    def test_lectura_de_desarrollo_se_normaliza_segun_los_recuadros(self):
        prueba = asistentes.validar_prueba({"preguntas": [SELECCION, DESARROLLO, DESARROLLO]})

        lecturas = asistentes.validar_lectura({"respuestas": [
            {"pregunta": 1, "marcada": "B", "estado": "respondida"},
            {"pregunta": 2, "tipo": "desarrollo", "desarrollo": "4 × 6", "formula": "", "resultado": "24",
             "estado": "respondida"},
            {"pregunta": 3, "tipo": "desarrollo", "desarrollo": "", "formula": "", "resultado": "",
             "estado": "respondida"},
        ]}, prueba)

        self.assertEqual(lecturas[0]["marcada"], 1)
        self.assertEqual(lecturas[1]["estado"], "parcial")
        self.assertEqual(lecturas[1]["transcripcion"], {"desarrollo": "4 × 6", "formula": "", "resultado": "24"})
        self.assertEqual(lecturas[2]["estado"], "en_blanco")

    def test_la_sugerencia_de_la_ia_se_acota_al_maximo(self):
        pregunta = asistentes.validar_prueba({"preguntas": [DESARROLLO]})["preguntas"][0]

        evaluacion = asistentes.validar_evaluacion(
            {"puntajes": {"desarrollo": "1,5", "formula": 7, "resultado": "no"}, "coherencia": "Revisar: x"}, pregunta)

        self.assertEqual(evaluacion["sugerencia"], {"desarrollo": 1.5, "formula": 1})
        self.assertEqual(evaluacion["coherencia"], "Revisar: x")


class PruebaConDesarrolloTests(AsistenteIATestBase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.usuario_docente)
        self.client.post(reverse("ia_crear_prueba"), {
            "carga": self.carga.pk, "objetivo": "OA 7: multiplicación", "tema": "multiplicación",
            "cantidad": 3, "cantidad_desarrollo": 2, "dificultad": "media",
        })
        self.prueba = InstrumentoIA.objects.get()

    def post_editor(self, accion, **cambios):
        datos = {"accion": accion, "titulo": self.prueba.contenido["titulo"],
                 "instrucciones": self.prueba.contenido["instrucciones"]}
        for i, pregunta in enumerate(self.prueba.contenido["preguntas"]):
            datos[f"p{i}_tipo"] = pregunta["tipo"]
            datos[f"p{i}_enunciado"] = pregunta["enunciado"]
            datos[f"p{i}_explicacion"] = pregunta.get("explicacion", "")
            if pregunta["tipo"] == "desarrollo":
                for campo in ("formula", "desarrollo_esperado", "resultado"):
                    datos[f"p{i}_{campo}"] = pregunta[campo]
                for j, criterio in enumerate(pregunta["criterios"]):
                    datos[f"p{i}_c{j}_clave"] = criterio["clave"]
                    datos[f"p{i}_c{j}_nombre"] = criterio["nombre"]
                    datos[f"p{i}_c{j}_puntaje"] = str(criterio["puntaje_maximo"])
                    datos[f"p{i}_c{j}_descriptor"] = criterio["descriptor"]
            else:
                datos[f"p{i}_correcta"] = str(pregunta["correcta"])
                for j, alternativa in enumerate(pregunta["alternativas"]):
                    datos[f"p{i}_alt{j}"] = alternativa
        datos.update(cambios)
        return self.client.post(reverse("ia_instrumento", args=[self.prueba.pk]), datos)

    def aprobar(self):
        self.post_editor("aprobar")
        self.prueba.refresh_from_db()

    def test_genera_preguntas_de_desarrollo_con_pauta(self):
        preguntas = self.prueba.contenido["preguntas"]

        self.assertEqual([p["tipo"] for p in preguntas], ["seleccion"] * 3 + ["desarrollo"] * 2)
        self.assertEqual(preguntas[3]["formula"], "Total = filas × lechugas por fila")
        self.assertEqual([c["nombre"] for c in preguntas[3]["criterios"]],
                         ["Desarrollo del cálculo", "Fórmula utilizada", "Resultado"])
        self.assertIn("la fórmula", self.prueba.contenido["instrucciones"])

    def test_el_editor_muestra_y_conserva_el_desarrollo(self):
        response = self.client.get(reverse("ia_instrumento", args=[self.prueba.pk]))
        self.assertContains(response, "Pregunta 4 · Desarrollo")
        self.assertContains(response, "Puntaje total de la prueba: <strong>11 puntos</strong>", html=False)
        self.assertContains(response, 'id="plantilla-desarrollo"')

        self.post_editor("guardar", p3_formula="12 × 8", p3_c0_puntaje="3", p4_c1_nombre="")

        self.prueba.refresh_from_db()
        cuarta, quinta = self.prueba.contenido["preguntas"][3:]
        self.assertEqual(cuarta["formula"], "12 × 8")
        self.assertEqual(cuarta["puntaje"], 5)
        self.assertEqual([c["clave"] for c in quinta["criterios"]], ["desarrollo", "resultado"])

    def test_agregar_una_pregunta_de_desarrollo_desde_el_editor(self):
        self.post_editor("guardar", p5_tipo="desarrollo", p5_enunciado="Explica cómo calculas 15 × 4.",
                         p5_formula="", p5_desarrollo_esperado="", p5_resultado="60",
                         p5_c0_clave="desarrollo", p5_c0_nombre="Desarrollo", p5_c0_puntaje="2",
                         p5_c2_clave="resultado", p5_c2_nombre="Resultado", p5_c2_puntaje="1")

        self.prueba.refresh_from_db()
        nueva = self.prueba.contenido["preguntas"][5]
        self.assertEqual((nueva["tipo"], nueva["puntaje"]), ("desarrollo", 3))

    def test_version_estudiante_tiene_recuadros_sin_pauta(self):
        self.aprobar()

        estudiante = self.client.get(reverse("ia_imprimir", args=[self.prueba.pk, "estudiante"]))
        docente = self.client.get(reverse("ia_imprimir", args=[self.prueba.pk, "docente"]))

        for rotulo in ("P4 · DESARROLLO DEL CÁLCULO", "P4 · FÓRMULA UTILIZADA", "P5 · RESULTADO",
                       "Puntaje total: 11 puntos"):
            self.assertContains(estudiante, rotulo)
        for pauta in ("Total = filas × lechugas por fila", "96 lechugas"):
            self.assertNotContains(estudiante, pauta)
            self.assertContains(docente, pauta)
        documento = contexto_documento(self.prueba, "estudiante")["documento"]
        self.assertNotIn("formula", documento["preguntas"][3])
        self.assertNotIn("descriptor", documento["preguntas"][3]["criterios"][0])

    def test_lectura_transcribe_y_sugiere_puntaje_sin_enviar_la_pauta_al_leer(self):
        self.aprobar()
        url = reverse("ia_corregir_prueba", args=[self.prueba.pk])
        original = asistentes.generar
        with mock.patch("colegio.ia.asistentes.generar", side_effect=original) as generar:
            self.client.post(url, {"accion": "leer", "alumno": self.alumno.pk, "archivos": [hoja()]})

        lectura, *evaluaciones = generar.call_args_list
        enviado_lectura = lectura.args[0] + lectura.args[1][0]["texto"]
        self.assertIn("[DESARROLLO", enviado_lectura)
        self.assertIn('"P4 · FÓRMULA UTILIZADA" -> campo "formula"', enviado_lectura)
        for pauta in ("96 lechugas", "Total = filas × lechugas por fila", "Josefa"):
            self.assertNotIn(pauta, enviado_lectura)
        self.assertEqual(len(evaluaciones), 2)
        enviado_evaluacion = evaluaciones[0].args[1][0]["texto"]
        self.assertIn("96 lechugas", enviado_evaluacion)
        self.assertNotIn("archivos", evaluaciones[0].args[1][0])
        self.assertNotIn("Josefa", enviado_evaluacion)

        # La traza de la lectura conserva el archivo y la lectura principal aunque
        # después se hayan hecho las llamadas de sugerencia de puntaje.
        registro = next(r for r in apps.get_model("colegio", "RegistroIA").objects.all() if r.lectura)
        self.assertEqual(len(registro.archivos), 1)
        self.assertTrue(any(item.get("tipo") == "desarrollo" for item in registro.lectura))
        self.assertNotIn("80 + 16", str(registro.lectura))

    def test_flujo_completo_con_desarrollo(self):
        self.aprobar()
        url = reverse("ia_corregir_prueba", args=[self.prueba.pk])
        from .views_trabajos import enlace_resultado
        self.client.post(url, {"accion": "leer", "alumno": self.alumno.pk, "archivos": [hoja()]})
        trabajo = apps.get_model("colegio", "TrabajoIA").objects.filter(operacion="lectura").get()

        response = self.client.get(enlace_resultado(trabajo))
        filas = response.context["filas"]
        self.assertEqual(filas[3][1]["transcripcion"]["resultado"], "96")
        self.assertEqual(filas[3][1]["sugerencia"], {"desarrollo": 2, "formula": 1, "resultado": 1})
        self.assertEqual(response.context["por_revisar"], 1)  # la pregunta 3 en blanco
        self.assertContains(response, 'name="r4_formula"')
        self.assertContains(response, "Ver pauta (4 pts)")

        datos = {"accion": "calcular", "alumno": self.alumno.pk, "leida_con_ia": "1", "trabajo": str(trabajo.pk),
                 "r1": "1", "ia1": "1", "r2": "2", "ia2": "2", "r3": "", "ia3": ""}
        for numero in (4, 5):
            for clave, sugerido in (("desarrollo", "2"), ("formula", "1"), ("resultado", "1")):
                datos[f"r{numero}_{clave}"] = sugerido
                datos[f"ia{numero}_{clave}"] = sugerido
        datos.update(r5_desarrollo="1", r5_resultado="0")  # el docente ajusta dos criterios
        response = self.client.post(url, datos)

        correccion = CorreccionPrueba.objects.get()
        self.assertRedirects(response, reverse("ia_correccion", args=[correccion.pk]))
        self.assertEqual((float(correccion.puntaje_obtenido), float(correccion.puntaje_maximo)), (8.0, 11.0))
        self.assertEqual(correccion.ajustes_docente, 2)
        self.assertEqual(correccion.correctas, 2)
        self.assertEqual(float(correccion.nota), asistentes.nota_chilena(8, 11))
        self.assertEqual(correccion.respuestas[4]["estado"], "parcial")
        self.assertEqual(correccion.respuestas[3]["transcripcion"]["formula"], "filas × lechugas por fila")

        resultado = self.client.get(reverse("ia_correccion", args=[correccion.pk]))
        self.assertContains(resultado, "8/11")
        self.assertContains(resultado, "Desarrollo: 2 de 4 puntos")
        self.assertContains(resultado, "Resultado esperado: <strong>96 lechugas</strong>", html=False)

    def test_ingreso_manual_muestra_puntajes_por_criterio(self):
        self.aprobar()
        url = reverse("ia_corregir_prueba", args=[self.prueba.pk])

        response = self.client.get(url, {"manual": "1"})

        self.assertContains(response, 'name="r5_desarrollo"')
        self.client.post(url, {"accion": "calcular", "leida_con_ia": "0", "r1": "1", "r2": "2", "r3": "3",
                               "r4_desarrollo": "2", "r4_formula": "1", "r4_resultado": "1"})
        correccion = CorreccionPrueba.objects.get()
        self.assertEqual(float(correccion.puntaje_obtenido), 7.0)
        self.assertEqual(correccion.respuestas[4]["estado"], "omitida")
        self.assertEqual(correccion.ajustes_docente, 0)

    def test_humanidades_usa_justificacion_y_conclusion(self):
        from .models import CargaAcademica
        carga = CargaAcademica.objects.create(curso=self.otro_curso, asignatura=self.asignatura_ajena,
                                              periodo=self.periodo, docente=self.docente)
        self.client.post(reverse("ia_crear_prueba"), {
            "carga": carga.pk, "objetivo": "OA 2", "tema": "la Independencia",
            "cantidad": 3, "cantidad_desarrollo": 1, "dificultad": "media",
        })
        prueba = InstrumentoIA.objects.get(carga=carga)

        nombres = [c["nombre"] for c in prueba.contenido["preguntas"][3]["criterios"]]
        self.assertEqual(nombres, ["Desarrollo / justificación", "Concepto o evidencia clave", "Conclusión"])
        self.assertIn("tu justificación", prueba.contenido["instrucciones"])
