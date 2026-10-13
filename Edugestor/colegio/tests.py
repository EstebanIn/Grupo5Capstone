from io import StringIO

from django.test import TestCase as DjangoTestCase
from django.core.exceptions import ValidationError
from django.urls import reverse

from .forms import CursoForm
from .models import (
    Alumno,
    Asignatura,
    Asistencia,
    CargaAcademica,
    Curso,
    Docente,
    Evaluacion,
    Matricula,
    Nota,
    PeriodoAcademico,
    Usuario,
)
from .models import Institucion, SolicitudPostulacion
from .tenancy import activar_institucion, desactivar_institucion


class TestCase(DjangoTestCase):
    """Cada clase de pruebas trabaja dentro de una institución activa."""

    @classmethod
    def setUpTestData(cls):
        cls.institucion = Institucion.objects.create(nombre="Colegio de Pruebas", slug="colegio-pruebas")
        cls._token_institucion = activar_institucion(cls.institucion)

    @classmethod
    def tearDownClass(cls):
        desactivar_institucion(cls._token_institucion)
        super().tearDownClass()


class CursoValidationTests(TestCase):
    def test_basica_permite_niveles_1_a_8(self):
        form = CursoForm(data={
            "ciclo": Curso.CICLO_BASICA,
            "nivel": 8,
            "seccion": "a",
            "estado_curso": "on",
        })

        self.assertTrue(form.is_valid(), form.errors.as_text())
        self.assertEqual(form.cleaned_data["seccion"], "A")

    def test_basica_rechaza_nivel_mayor_a_8(self):
        form = CursoForm(data={
            "ciclo": Curso.CICLO_BASICA,
            "nivel": 9,
            "seccion": "A",
            "estado_curso": "on",
        })

        self.assertFalse(form.is_valid())
        self.assertIn("nivel", form.errors)

    def test_media_permite_solo_niveles_1_a_4(self):
        form = CursoForm(data={
            "ciclo": Curso.CICLO_MEDIA,
            "nivel": 5,
            "seccion": "A",
            "estado_curso": "on",
        })

        self.assertFalse(form.is_valid())
        self.assertIn("nivel", form.errors)

    def test_kinder_es_un_curso_valido(self):
        curso = Curso(ciclo=Curso.CICLO_KINDER, nivel=1, seccion="b")
        curso.full_clean()

        self.assertEqual(curso.seccion, "B")
        self.assertEqual(str(curso), "Kinder B")
        self.assertEqual(curso.nivel_label, "Kinder")

    def test_kinder_rechaza_niveles_distintos_de_1(self):
        curso = Curso(ciclo=Curso.CICLO_KINDER, nivel=2, seccion="A")

        with self.assertRaises(ValidationError):
            curso.full_clean()


class CursoProfesorJefeFormTests(TestCase):
    def setUp(self):
        self.admin = Usuario.objects.create_user(
            username="admin_jefatura",
            password="pass",
            rut="12.000.000-0",
            tipo_usuario="ADMIN",
        )
        usuario_docente = Usuario.objects.create_user(
            username="docente_jefe_form",
            password="pass",
            rut="10.111.111-1",
            tipo_usuario="DOCENTE",
            first_name="Souta",
            last_name="Janjarri",
            email="jefeform@colegio.cl",
        )
        self.docente = Docente.objects.get(usuario=usuario_docente)
        self.docente.nombre_docente = "Souta"
        self.docente.apellido_docente = "Janjarri"
        self.docente.email_institucional = "jefeform@colegio.cl"
        self.docente.save()
        usuario_otro_docente = Usuario.objects.create_user(
            username="otro_docente_jefe_form",
            password="pass",
            rut="10.222.222-2",
            tipo_usuario="DOCENTE",
            first_name="gnomo",
            last_name="Ferrada",
            email="otrojefeform@colegio.cl",
        )
        self.otro_docente = Docente.objects.get(usuario=usuario_otro_docente)
        self.otro_docente.nombre_docente = "gnomo"
        self.otro_docente.apellido_docente = "Ferrada"
        self.otro_docente.email_institucional = "otrojefeform@colegio.cl"
        self.otro_docente.save()

    def test_guarda_profesor_jefe_del_curso(self):
        form = CursoForm(data={
            "ciclo": Curso.CICLO_BASICA,
            "nivel": 1,
            "seccion": "A",
            "estado_curso": "on",
            "profesor_jefe": self.docente.pk,
        })

        self.assertTrue(form.is_valid(), form.errors.as_text())
        curso = form.save()

        self.assertEqual(curso.profesor_jefe, self.docente)

    def test_permite_desasignar_profesor_jefe(self):
        curso = Curso.objects.create(
            ciclo=Curso.CICLO_BASICA,
            nivel=1,
            seccion="B",
            profesor_jefe=self.docente,
        )
        form = CursoForm(data={
            "ciclo": Curso.CICLO_BASICA,
            "nivel": 1,
            "seccion": "B",
            "estado_curso": "on",
            "profesor_jefe": "",
        }, instance=curso)

        self.assertTrue(form.is_valid(), form.errors.as_text())
        curso = form.save()

        self.assertIsNone(curso.profesor_jefe)

    def test_reemplaza_profesor_jefe_sin_acumular_mas_de_un_docente(self):
        curso = Curso.objects.create(
            ciclo=Curso.CICLO_BASICA,
            nivel=1,
            seccion="C",
            profesor_jefe=self.docente,
        )
        form = CursoForm(data={
            "ciclo": Curso.CICLO_BASICA,
            "nivel": 1,
            "seccion": "C",
            "estado_curso": "on",
            "profesor_jefe": self.otro_docente.pk,
        }, instance=curso)

        self.assertTrue(form.is_valid(), form.errors.as_text())
        curso = form.save()

        self.assertEqual(curso.profesor_jefe, self.otro_docente)
        self.assertNotEqual(curso.profesor_jefe, self.docente)

    def test_editar_curso_muestra_buscador_de_profesor_jefe(self):
        curso = Curso.objects.create(
            ciclo=Curso.CICLO_BASICA,
            nivel=2,
            seccion="A",
            profesor_jefe=self.docente,
        )
        self.client.force_login(self.admin)

        response = self.client.get(reverse("editar_curso", args=[curso.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "profesor-jefe-search")
        self.assertContains(response, "Souta Janjarri")

    def test_editar_curso_guarda_profesor_jefe_desde_la_vista(self):
        curso = Curso.objects.create(
            ciclo=Curso.CICLO_BASICA,
            nivel=2,
            seccion="B",
        )
        self.client.force_login(self.admin)

        response = self.client.post(reverse("editar_curso", args=[curso.pk]), {
            "ciclo": Curso.CICLO_BASICA,
            "nivel": 2,
            "seccion": "B",
            "estado_curso": "on",
            "profesor_jefe": self.docente.pk,
        })
        curso.refresh_from_db()

        self.assertEqual(response.status_code, 302)
        self.assertEqual(curso.profesor_jefe, self.docente)


class PanelAdminDocentesTests(TestCase):
    def test_muestra_curso_donde_docente_es_profesor_jefe(self):
        admin = Usuario.objects.create_user(
            username="admin_docentes",
            password="pass",
            rut="12.333.333-3",
            tipo_usuario="ADMIN",
        )
        usuario_docente = Usuario.objects.create_user(
            username="docente_con_jefatura",
            password="pass",
            rut="13.333.333-3",
            tipo_usuario="DOCENTE",
            first_name="Souta",
            last_name="Janjarri",
            email="conjefatura@colegio.cl",
        )
        docente = Docente.objects.get(usuario=usuario_docente)
        docente.nombre_docente = "Souta"
        docente.apellido_docente = "Janjarri"
        docente.email_institucional = "conjefatura@colegio.cl"
        docente.save()
        Usuario.objects.create_user(
            username="docente_sin_jefatura_admin",
            password="pass",
            rut="14.333.333-3",
            tipo_usuario="DOCENTE",
            first_name="Otro",
            last_name="Docente",
            email="sinjefatura@colegio.cl",
        )
        curso = Curso.objects.create(
            ciclo=Curso.CICLO_BASICA,
            nivel=1,
            seccion="A",
            profesor_jefe=docente,
        )

        self.client.force_login(admin)
        response = self.client.get(reverse("panel_admin_docentes"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Profesor jefe de")
        self.assertContains(response, str(curso))
        self.assertContains(response, "Sin jefatura")


class EditarAsignaturaDocentesTests(TestCase):
    def setUp(self):
        self.admin = Usuario.objects.create_user(
            username="admin",
            password="pass",
            rut="12.345.678-5",
            tipo_usuario="ADMIN",
        )
        usuario_docente = Usuario.objects.create_user(
            username="docente1",
            password="pass",
            rut="11.111.111-1",
            tipo_usuario="DOCENTE",
            first_name="Souta",
            last_name="Janjarri",
            email="souta@colegio.cl",
        )
        self.docente = Docente.objects.get(usuario=usuario_docente)
        self.docente.nombre_docente = "Souta"
        self.docente.apellido_docente = "Janjarri"
        self.docente.email_institucional = "souta@colegio.cl"
        self.docente.save()

        self.curso = Curso.objects.create(ciclo=Curso.CICLO_BASICA, nivel=1, seccion="A")
        self.periodo = PeriodoAcademico.objects.create(anio=2026, semestre=1)
        self.asignatura = Asignatura.objects.create(
            nombre_asignatura="Matematicas",
            descripcion="",
            curso=self.curso,
            estado_asignatura=True,
        )
        self.asignatura.docentes.add(self.docente)
        self.carga = CargaAcademica.objects.create(
            curso=self.curso,
            asignatura=self.asignatura,
            periodo=self.periodo,
            docente=self.docente,
        )

    def test_desmarcar_docente_sin_historial_lo_desasigna_de_la_asignatura_y_carga(self):
        self.client.force_login(self.admin)

        response = self.client.post(reverse("editar_asignatura", args=[self.asignatura.pk]), {
            "nombre_asignatura": "Matematicas",
            "descripcion": "",
            "curso": self.curso.pk,
            "estado_asignatura": "True",
        })

        self.assertEqual(response.status_code, 302)
        self.asignatura.refresh_from_db()
        self.assertFalse(self.asignatura.docentes.filter(pk=self.docente.pk).exists())
        self.assertFalse(CargaAcademica.objects.filter(pk=self.carga.pk).exists())


class PanelAsignaturasFiltroTests(TestCase):
    def setUp(self):
        self.admin = Usuario.objects.create_user(
            username="admin",
            password="pass",
            rut="12.345.678-5",
            tipo_usuario="ADMIN",
        )
        self.basica = Curso.objects.create(ciclo=Curso.CICLO_BASICA, nivel=1, seccion="A")
        self.media = Curso.objects.create(ciclo=Curso.CICLO_MEDIA, nivel=1, seccion="A")
        self.matematicas_basica = Asignatura.objects.create(
            nombre_asignatura="Matematicas",
            descripcion="",
            curso=self.basica,
            estado_asignatura=True,
        )
        Asignatura.objects.create(
            nombre_asignatura="Matematicas",
            descripcion="",
            curso=self.media,
            estado_asignatura=True,
        )
        Asignatura.objects.create(
            nombre_asignatura="Biologia",
            descripcion="",
            curso=self.basica,
            estado_asignatura=True,
        )

    def test_filtra_por_nombre_de_asignatura_y_ciclo(self):
        self.client.force_login(self.admin)

        response = self.client.get(reverse("panel_admin_asignaturas"), {
            "asignatura": "Matematicas",
            "ciclo": Curso.CICLO_BASICA,
        })

        asignaturas = list(response.context["asignaturas"])
        self.assertEqual(asignaturas, [self.matematicas_basica])
        self.assertIn("Matematicas", response.context["nombres_asignaturas"])
        self.assertIn("Biologia", response.context["nombres_asignaturas"])


class PanelAlumnoMallaCursoTests(TestCase):
    """Pruebas de la malla por curso que ve el alumno en Mis Asignaturas."""

    def setUp(self):
        self.usuario_alumno = Usuario.objects.create_user(
            username="alumno1",
            password="pass",
            rut="22.222.222-2",
            tipo_usuario="ALUMNO",
            first_name="Jasper",
            last_name="Alumno",
        )
        self.alumno = Alumno.objects.get(usuario=self.usuario_alumno)
        self.curso = Curso.objects.create(ciclo=Curso.CICLO_BASICA, nivel=1, seccion="A")
        self.otro_curso = Curso.objects.create(ciclo=Curso.CICLO_BASICA, nivel=2, seccion="A")
        self.periodo = PeriodoAcademico.objects.create(anio=2026, semestre=1)
        Matricula.objects.create(
            alumno=self.alumno,
            curso=self.curso,
            periodo=self.periodo,
            estado="Activa",
        )
        self.quimica = Asignatura.objects.create(
            nombre_asignatura="Quimica",
            descripcion="",
            curso=self.curso,
            estado_asignatura=True,
        )
        # Esta asignatura pertenece a otro curso y no debe aparecer para el alumno.
        Asignatura.objects.create(
            nombre_asignatura="Historia",
            descripcion="",
            curso=self.otro_curso,
            estado_asignatura=True,
        )

    def test_muestra_malla_del_curso_aunque_la_asignatura_no_tenga_docente(self):
        # La asignatura pertenece al curso del alumno, por eso aparece aunque no tenga docentes.
        self.client.force_login(self.usuario_alumno)

        response = self.client.get(reverse("panel_alumno_asignaturas"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context["asignaturas"]), [self.quimica])
        self.assertEqual(response.context["total_asignaturas"], 1)
        self.assertContains(response, "Quimica")
        self.assertContains(response, "Sin docente asignado")
        self.assertNotContains(response, "Historia")


class PanelAlumnoAsistenciaTests(TestCase):
    def setUp(self):
        usuario_alumno = Usuario.objects.create_user(
            username="alumno_asistencia",
            password="pass",
            rut="66.666.666-6",
            tipo_usuario="ALUMNO",
            first_name="Albert",
            last_name="Enstein",
        )
        usuario_docente = Usuario.objects.create_user(
            username="docente_asistencia",
            password="pass",
            rut="77.777.777-7",
            tipo_usuario="DOCENTE",
            first_name="Souta",
            last_name="Janjarri",
            email="asistencia@colegio.cl",
        )
        self.alumno = Alumno.objects.get(usuario=usuario_alumno)
        self.alumno.nombre_alumno = "Albert"
        self.alumno.apellido_alumno = "Enstein"
        self.alumno.save()
        docente = Docente.objects.get(usuario=usuario_docente)
        docente.nombre_docente = "Souta"
        docente.apellido_docente = "Janjarri"
        docente.email_institucional = "asistencia@colegio.cl"
        docente.save()

        curso = Curso.objects.create(ciclo=Curso.CICLO_BASICA, nivel=1, seccion="B")
        periodo = PeriodoAcademico.objects.create(anio=2026, semestre=1)
        Matricula.objects.create(
            alumno=self.alumno,
            curso=curso,
            periodo=periodo,
            estado="Activa",
        )

        self.lenguaje = Asignatura.objects.create(
            nombre_asignatura="Lenguaje",
            curso=curso,
            estado_asignatura=True,
        )
        matematicas = Asignatura.objects.create(
            nombre_asignatura="Matematicas",
            curso=curso,
            estado_asignatura=True,
        )
        carga_lenguaje = CargaAcademica.objects.create(
            curso=curso,
            asignatura=self.lenguaje,
            periodo=periodo,
            docente=docente,
        )
        carga_matematicas = CargaAcademica.objects.create(
            curso=curso,
            asignatura=matematicas,
            periodo=periodo,
            docente=docente,
        )
        Asistencia.objects.create(
            alumno=self.alumno,
            carga=carga_lenguaje,
            fecha="2026-06-29",
            estado_asistencia="Presente",
        )
        Asistencia.objects.create(
            alumno=self.alumno,
            carga=carga_matematicas,
            fecha="2026-06-28",
            estado_asistencia="Ausente",
        )

    def test_filtra_asistencia_por_asignatura(self):
        self.client.force_login(self.alumno.usuario)

        response = self.client.get(reverse("panel_alumno_asistencia"), {
            "asignatura": self.lenguaje.pk,
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total"], 1)
        self.assertEqual(response.context["presentes"], 1)
        self.assertEqual(response.context["ausentes"], 0)
        self.assertEqual(
            list(response.context["registros"].values_list("carga__asignatura", flat=True)),
            [self.lenguaje.pk],
        )
        self.assertContains(response, "Lenguaje")


class PanelAlumnoNotasTests(TestCase):
    def test_muestra_notas_agrupadas_por_asignatura_desplegable(self):
        usuario_alumno = Usuario.objects.create_user(
            username="alumno_notas_ramo",
            password="pass",
            rut="21.111.111-1",
            tipo_usuario="ALUMNO",
            first_name="Albert",
            last_name="Enstein",
        )
        usuario_docente = Usuario.objects.create_user(
            username="docente_notas_ramo",
            password="pass",
            rut="22.111.111-1",
            tipo_usuario="DOCENTE",
            first_name="Souta",
            last_name="Janjarri",
            email="notasramo@colegio.cl",
        )
        alumno = Alumno.objects.get(usuario=usuario_alumno)
        alumno.nombre_alumno = "Albert"
        alumno.apellido_alumno = "Enstein"
        alumno.save()
        docente = Docente.objects.get(usuario=usuario_docente)
        docente.nombre_docente = "Souta"
        docente.apellido_docente = "Janjarri"
        docente.email_institucional = "notasramo@colegio.cl"
        docente.save()

        curso = Curso.objects.create(ciclo=Curso.CICLO_BASICA, nivel=1, seccion="A")
        periodo = PeriodoAcademico.objects.create(anio=2026, semestre=1)
        Matricula.objects.create(alumno=alumno, curso=curso, periodo=periodo, estado="Activa")
        lenguaje = Asignatura.objects.create(
            nombre_asignatura="Lenguaje",
            curso=curso,
            estado_asignatura=True,
        )
        matematicas = Asignatura.objects.create(
            nombre_asignatura="Matematicas",
            curso=curso,
            estado_asignatura=True,
        )
        carga = CargaAcademica.objects.create(
            curso=curso,
            asignatura=matematicas,
            periodo=periodo,
            docente=docente,
        )
        evaluacion = Evaluacion.objects.create(
            carga=carga,
            nombre_evaluacion="Nota 1",
            tipo_evaluacion="Prueba",
            porcentaje=0,
            fecha="2026-07-01",
            numero_evaluacion=1,
        )
        Nota.objects.create(evaluacion=evaluacion, alumno=alumno, valor_nota=6.5)

        self.client.force_login(usuario_alumno)
        response = self.client.get(reverse("panel_alumno_notas"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "subject-toggle")
        self.assertContains(response, "Lenguaje")
        self.assertContains(response, "Matematicas")
        self.assertContains(response, "Nota 1")
        self.assertContains(response, "Sin evaluaciones registradas para este ramo.")
        self.assertEqual(
            [grupo["asignatura"].nombre_asignatura for grupo in response.context["notas_por_asignatura"]],
            [lenguaje.nombre_asignatura, matematicas.nombre_asignatura],
        )
        self.assertEqual(response.context["notas_por_asignatura"][0]["notas"], [])
        self.assertEqual(float(response.context["notas_por_asignatura"][1]["notas"][0].valor_nota), 6.5)


class PanelAdminMatriculasTests(TestCase):
    def test_muestra_alumnos_creados_sin_matricula(self):
        admin = Usuario.objects.create_user(
            username="admin2",
            password="pass",
            rut="33.333.333-3",
            tipo_usuario="ADMIN",
        )
        usuario_alumno = Usuario.objects.create_user(
            username="albert",
            password="pass",
            rut="15.359.251-9",
            tipo_usuario="ALUMNO",
            first_name="Albert",
            last_name="Enstein",
        )
        alumno = Alumno.objects.get(usuario=usuario_alumno)
        alumno.nombre_alumno = "Albert"
        alumno.apellido_alumno = "Enstein"
        alumno.save()

        self.client.force_login(admin)
        response = self.client.get(reverse("panel_admin_matriculas"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Alumnos sin matr")
        self.assertContains(response, "Albert Enstein")
        self.assertContains(response, "Pendiente de matr")


class PanelAdminCursosTests(TestCase):
    def test_muestra_solo_las_matriculas_del_curso_clickeado(self):
        admin = Usuario.objects.create_user(
            username="admin_cursos",
            password="pass",
            rut="44.444.444-4",
            tipo_usuario="ADMIN",
        )
        periodo = PeriodoAcademico.objects.create(anio=2026, semestre=1)
        primero_a = Curso.objects.create(ciclo=Curso.CICLO_BASICA, nivel=1, seccion="A")
        primero_b = Curso.objects.create(ciclo=Curso.CICLO_BASICA, nivel=1, seccion="B")

        usuario_jasper = Usuario.objects.create_user(
            username="jasper",
            password="pass",
            rut="11.111.111-1",
            tipo_usuario="ALUMNO",
            first_name="Jasper",
            last_name="Ferrada",
        )
        usuario_albert = Usuario.objects.create_user(
            username="albert",
            password="pass",
            rut="15.359.251-9",
            tipo_usuario="ALUMNO",
            first_name="Albert",
            last_name="Enstein",
        )
        jasper = Alumno.objects.get(usuario=usuario_jasper)
        albert = Alumno.objects.get(usuario=usuario_albert)
        jasper.nombre_alumno = "Jasper"
        jasper.apellido_alumno = "Ferrada"
        jasper.save()
        albert.nombre_alumno = "Albert"
        albert.apellido_alumno = "Enstein"
        albert.save()

        Matricula.objects.create(alumno=jasper, curso=primero_a, periodo=periodo, estado="Activa")
        Matricula.objects.create(alumno=albert, curso=primero_b, periodo=periodo, estado="Activa")
        usuario_docente = Usuario.objects.create_user(
            username="docente_admin_cursos",
            password="pass",
            rut="16.359.251-9",
            tipo_usuario="DOCENTE",
            first_name="Souta",
            last_name="Janjarri",
            email="admincursos@colegio.cl",
        )
        docente = Docente.objects.get(usuario=usuario_docente)
        docente.nombre_docente = "Souta"
        docente.apellido_docente = "Janjarri"
        docente.email_institucional = "admincursos@colegio.cl"
        docente.save()
        matematicas = Asignatura.objects.create(
            nombre_asignatura="Matematicas",
            curso=primero_b,
            estado_asignatura=True,
        )
        Asignatura.objects.create(
            nombre_asignatura="Lenguaje",
            curso=primero_b,
            estado_asignatura=True,
        )
        carga = CargaAcademica.objects.create(
            curso=primero_b,
            asignatura=matematicas,
            periodo=periodo,
            docente=docente,
        )
        evaluacion = Evaluacion.objects.create(
            carga=carga,
            nombre_evaluacion="Nota 1",
            tipo_evaluacion="Prueba",
            porcentaje=0,
            fecha="2026-07-01",
            numero_evaluacion=1,
        )
        Nota.objects.create(evaluacion=evaluacion, alumno=albert, valor_nota=6.5)

        self.client.force_login(admin)
        response = self.client.get(reverse("panel_admin_cursos"), {"curso_id": primero_b.pk})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["curso_seleccionado"], primero_b)
        self.assertEqual(list(response.context["matriculas_curso"]), list(Matricula.objects.filter(curso=primero_b)))
        self.assertContains(response, "Alumnos de 1° Básico B")
        self.assertContains(response, "Albert Enstein")
        self.assertNotContains(response, "Jasper Ferrada")
        self.assertContains(response, 'data-modal-target="student-modal-')
        self.assertContains(response, "subject-grade-header")
        self.assertContains(response, "Notas por asignatura")
        self.assertContains(response, "Matematicas")
        self.assertContains(response, "Nota 1")
        self.assertContains(response, "6,50")
        self.assertContains(response, "Lenguaje")
        self.assertContains(response, "Sin notas registradas.")
        detalle_asignaturas = response.context["alumnos_curso_detalle"][0]["asignaturas_detalle"]
        self.assertEqual(
            [detalle["asignatura"].nombre_asignatura for detalle in detalle_asignaturas],
            ["Lenguaje", "Matematicas"],
        )


class PanelDocenteCursosNotasTests(TestCase):
    def test_link_ingresar_notas_envia_la_carga_del_curso_correcto(self):
        usuario_docente = Usuario.objects.create_user(
            username="docente_notas",
            password="pass",
            rut="55.555.555-5",
            tipo_usuario="DOCENTE",
            first_name="Souta",
            last_name="Janjarri",
            email="notas@colegio.cl",
        )
        docente = Docente.objects.get(usuario=usuario_docente)
        docente.nombre_docente = "Souta"
        docente.apellido_docente = "Janjarri"
        docente.email_institucional = "notas@colegio.cl"
        docente.save()

        periodo = PeriodoAcademico.objects.create(anio=2026, semestre=1)
        primero_a = Curso.objects.create(ciclo=Curso.CICLO_BASICA, nivel=1, seccion="A")
        primero_b = Curso.objects.create(ciclo=Curso.CICLO_BASICA, nivel=1, seccion="B")
        matematicas_a = Asignatura.objects.create(
            nombre_asignatura="Matematicas",
            curso=primero_a,
            estado_asignatura=True,
        )
        matematicas_b = Asignatura.objects.create(
            nombre_asignatura="Matematicas",
            curso=primero_b,
            estado_asignatura=True,
        )
        carga_a = CargaAcademica.objects.create(
            curso=primero_a,
            asignatura=matematicas_a,
            periodo=periodo,
            docente=docente,
        )
        carga_b = CargaAcademica.objects.create(
            curso=primero_b,
            asignatura=matematicas_b,
            periodo=periodo,
            docente=docente,
        )
        Evaluacion.objects.create(
            carga=carga_a,
            nombre_evaluacion="Nota A",
            tipo_evaluacion="Prueba",
            porcentaje=0,
            fecha="2026-06-01",
            numero_evaluacion=1,
        )
        evaluacion_b_1 = Evaluacion.objects.create(
            carga=carga_b,
            nombre_evaluacion="Nota B",
            tipo_evaluacion="Prueba",
            porcentaje=0,
            fecha="2026-07-12",
            numero_evaluacion=1,
        )
        evaluacion_b_2 = Evaluacion.objects.create(
            carga=carga_b,
            nombre_evaluacion="Nota C",
            tipo_evaluacion="Prueba",
            porcentaje=0,
            fecha="2026-06-18",
            numero_evaluacion=2,
        )
        usuario_alumno = Usuario.objects.create_user(
            username="alumno_notas",
            password="pass",
            rut="56.789.123-4",
            tipo_usuario="ALUMNO",
            first_name="Albert",
            last_name="Enstein",
        )
        alumno = Alumno.objects.get(usuario=usuario_alumno)
        alumno.nombre_alumno = "Albert"
        alumno.apellido_alumno = "Enstein"
        alumno.save()
        Matricula.objects.create(
            alumno=alumno,
            curso=primero_b,
            periodo=periodo,
            estado="Activa",
        )
        Nota.objects.create(evaluacion=evaluacion_b_1, alumno=alumno, valor_nota=5.5)
        Nota.objects.create(evaluacion=evaluacion_b_2, alumno=alumno, valor_nota=6.0)

        self.client.force_login(usuario_docente)
        cursos_response = self.client.get(reverse("panel_docente_cursos"))
        notas_sin_curso_response = self.client.get(reverse("panel_docente_notas"))
        notas_response = self.client.get(reverse("panel_docente_notas"), {"carga_id": carga_b.pk})

        self.assertContains(cursos_response, f"?carga_id={carga_b.pk}")
        self.assertContains(notas_sin_curso_response, "Selecciona un curso desde el panel")
        self.assertNotContains(notas_sin_curso_response, "Nota A")
        self.assertNotContains(notas_sin_curso_response, "Nota B")
        self.assertEqual(notas_response.context["carga_seleccionada"], carga_b)
        self.assertContains(notas_response, "Nota B")
        self.assertContains(notas_response, "Nota C")
        self.assertNotContains(notas_response, "Nota A")
        self.assertContains(notas_response, "Registro de Notas")
        self.assertNotContains(notas_response, "Registro de Notas ”")
        self.assertContains(notas_response, "Nota 1")
        self.assertContains(notas_response, "Nota 2")
        self.assertContains(notas_response, "grade-group-toggle")
        self.assertContains(notas_response, "Albert Enstein")
        self.assertEqual(
            list(notas_response.context["notas_registradas"].values_list("evaluacion__nombre_evaluacion", flat=True)),
            ["Nota B", "Nota C"],
        )
        self.assertEqual(
            list(notas_response.context["evaluaciones"].values_list("nombre_evaluacion", flat=True)),
            ["Nota B", "Nota C"],
        )
        self.assertEqual(
            [grupo["evaluacion"].numero_evaluacion for grupo in notas_response.context["notas_por_evaluacion"]],
            [1, 2],
        )
        self.assertEqual(
            [float(grupo["notas"][0].valor_nota) for grupo in notas_response.context["notas_por_evaluacion"]],
            [5.5, 6.0],
        )


class PanelDocenteAsistenciaTests(TestCase):
    def setUp(self):
        self.usuario_docente = Usuario.objects.create_user(
            username="docente_control_asistencia",
            password="pass",
            rut="88.888.888-8",
            tipo_usuario="DOCENTE",
            first_name="Souta",
            last_name="Janjarri",
            email="control@colegio.cl",
        )
        docente = Docente.objects.get(usuario=self.usuario_docente)
        docente.nombre_docente = "Souta"
        docente.apellido_docente = "Janjarri"
        docente.email_institucional = "control@colegio.cl"
        docente.save()

        usuario_alumno = Usuario.objects.create_user(
            username="alumno_control_asistencia",
            password="pass",
            rut="99.999.999-9",
            tipo_usuario="ALUMNO",
            first_name="Albert",
            last_name="Enstein",
        )
        self.alumno = Alumno.objects.get(usuario=usuario_alumno)
        self.alumno.nombre_alumno = "Albert"
        self.alumno.apellido_alumno = "Enstein"
        self.alumno.save()

        self.curso = Curso.objects.create(ciclo=Curso.CICLO_BASICA, nivel=1, seccion="A")
        self.periodo = PeriodoAcademico.objects.create(anio=2026, semestre=1)
        self.asignatura = Asignatura.objects.create(
            nombre_asignatura="Lenguaje",
            curso=self.curso,
            estado_asignatura=True,
        )
        self.carga = CargaAcademica.objects.create(
            curso=self.curso,
            asignatura=self.asignatura,
            periodo=self.periodo,
            docente=docente,
        )
        Matricula.objects.create(
            alumno=self.alumno,
            curso=self.curso,
            periodo=self.periodo,
            estado="Activa",
        )

    def test_presente_no_guarda_observacion(self):
        self.client.force_login(self.usuario_docente)

        response = self.client.post(reverse("panel_docente_asistencia"), {
            "guardar": "1",
            "carga_id": self.carga.pk,
            "fecha": "2026-06-29",
            f"estado_{self.alumno.pk}": "Presente",
            f"obs_{self.alumno.pk}": "Texto que no debe guardarse",
        })

        self.assertEqual(response.status_code, 302)
        asistencia = Asistencia.objects.get(alumno=self.alumno, carga=self.carga)
        self.assertEqual(asistencia.estado_asistencia, "Presente")
        self.assertIsNone(asistencia.observacion)

    def test_ausente_si_guarda_observacion(self):
        self.client.force_login(self.usuario_docente)

        response = self.client.post(reverse("panel_docente_asistencia"), {
            "guardar": "1",
            "carga_id": self.carga.pk,
            "fecha": "2026-06-29",
            f"estado_{self.alumno.pk}": "Ausente",
            f"obs_{self.alumno.pk}": "Aviso del apoderado pendiente",
        })

        self.assertEqual(response.status_code, 302)
        asistencia = Asistencia.objects.get(alumno=self.alumno, carga=self.carga)
        self.assertEqual(asistencia.estado_asistencia, "Ausente")
        self.assertEqual(asistencia.observacion, "Aviso del apoderado pendiente")


class PanelDocenteJefaturaTests(TestCase):
    def setUp(self):
        self.usuario_docente = Usuario.objects.create_user(
            username="profesor_jefe",
            password="pass",
            rut="10.000.000-1",
            tipo_usuario="DOCENTE",
            first_name="Souta",
            last_name="Janjarri",
            email="jefe@colegio.cl",
        )
        self.docente = Docente.objects.get(usuario=self.usuario_docente)
        self.docente.nombre_docente = "Souta"
        self.docente.apellido_docente = "Janjarri"
        self.docente.email_institucional = "jefe@colegio.cl"
        self.docente.save()

        self.periodo = PeriodoAcademico.objects.create(anio=2026, semestre=1)
        self.curso = Curso.objects.create(
            ciclo=Curso.CICLO_BASICA,
            nivel=1,
            seccion="A",
            profesor_jefe=self.docente,
        )
        self.asignatura = Asignatura.objects.create(
            nombre_asignatura="Matematicas",
            curso=self.curso,
            estado_asignatura=True,
        )
        self.asignatura_sin_notas = Asignatura.objects.create(
            nombre_asignatura="Lenguaje",
            curso=self.curso,
            estado_asignatura=True,
        )
        self.carga = CargaAcademica.objects.create(
            curso=self.curso,
            asignatura=self.asignatura,
            periodo=self.periodo,
            docente=self.docente,
        )
        self.evaluacion = Evaluacion.objects.create(
            carga=self.carga,
            nombre_evaluacion="Nota 1",
            tipo_evaluacion="Prueba",
            porcentaje=0,
            fecha="2026-07-01",
            numero_evaluacion=1,
        )

        usuario_alumno = Usuario.objects.create_user(
            username="alumno_jefatura",
            password="pass",
            rut="20.000.000-2",
            tipo_usuario="ALUMNO",
            first_name="Albert",
            last_name="Enstein",
        )
        self.alumno = Alumno.objects.get(usuario=usuario_alumno)
        self.alumno.nombre_alumno = "Albert"
        self.alumno.apellido_alumno = "Enstein"
        self.alumno.save()
        Matricula.objects.create(
            alumno=self.alumno,
            curso=self.curso,
            periodo=self.periodo,
            estado="Activa",
        )
        Nota.objects.create(evaluacion=self.evaluacion, alumno=self.alumno, valor_nota=6.0)
        Asistencia.objects.create(
            alumno=self.alumno,
            carga=self.carga,
            fecha="2026-07-01",
            estado_asistencia="Presente",
        )
        Asistencia.objects.create(
            alumno=self.alumno,
            carga=self.carga,
            fecha="2026-07-02",
            estado_asistencia="Ausente",
        )

    def test_menu_muestra_profesor_jefe_solo_si_tiene_jefatura(self):
        usuario_sin_jefatura = Usuario.objects.create_user(
            username="docente_sin_jefatura",
            password="pass",
            rut="30.000.000-3",
            tipo_usuario="DOCENTE",
            first_name="Otro",
            last_name="Docente",
            email="otro@colegio.cl",
        )

        self.client.force_login(self.usuario_docente)
        response_con_jefatura = self.client.get(reverse("panel_docente"))

        self.client.force_login(usuario_sin_jefatura)
        response_sin_jefatura = self.client.get(reverse("panel_docente"))

        self.assertContains(response_con_jefatura, "Profesor Jefe")
        self.assertNotContains(response_sin_jefatura, "Profesor Jefe")

    def test_panel_jefatura_usa_notas_y_asistencia_de_la_base_de_datos(self):
        self.client.force_login(self.usuario_docente)

        response = self.client.get(reverse("panel_docente_jefatura"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["curso"], self.curso)
        self.assertEqual(response.context["total_alumnos"], 1)
        self.assertEqual(response.context["promedio_general"], 6.0)
        self.assertEqual(response.context["asistencia_general"], 50.0)
        self.assertContains(response, "Albert Enstein")
        self.assertContains(response, 'data-modal-target="student-modal-')
        self.assertContains(response, "subject-grade-header")
        self.assertContains(response, "Notas por asignatura")
        self.assertContains(response, "Matematicas")
        self.assertContains(response, "Nota 1")
        self.assertContains(response, "Lenguaje")
        self.assertContains(response, "Sin notas registradas.")
        self.assertContains(response, "Cerrar")
        detalle_asignaturas = response.context["alumnos_resumen"][0]["asignaturas_detalle"]
        self.assertEqual(
            [detalle["asignatura"].nombre_asignatura for detalle in detalle_asignaturas],
            ["Lenguaje", "Matematicas"],
        )




# ============================================================
# DATOS SINTÉTICOS Y MULTI-INSTITUCIÓN
# Estas clases usan DjangoTestCase: trabajan sin institución activa, como el
# comando de gestión, y activan cada institución explícitamente.
# ============================================================
from django.apps import apps
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError

from .tenancy import InstitucionCruzadaError, institucion_activa


def generar_datos(*args):
    call_command("generar_datos_sinteticos", *args, stdout=StringIO())


class GenerarDatosSinteticosTests(DjangoTestCase):
    def _resumen(self):
        return {
            "usuarios": sorted(Usuario.objects.values_list("username", "rut", "institucion__slug")),
            "notas": sorted(
                Nota.objects.values_list("alumno__usuario__username", "evaluacion__nombre_evaluacion", "valor_nota")
            ),
            "asistencia": sorted(
                Asistencia.objects.values_list("alumno__usuario__username", "fecha", "estado_asistencia")
            ),
        }

    def test_genera_tres_instituciones_coherentes_y_ruts_validos(self):
        from .validators import validar_rut_chileno

        generar_datos("--alumnos-por-curso", "3")

        self.assertEqual(Institucion.objects.count(), 3)
        for institucion in Institucion.objects.all():
            with institucion_activa(institucion):
                self.assertEqual(Curso.objects.count(), 9)
                self.assertEqual(Alumno.objects.count(), 27)
                self.assertEqual(Matricula.objects.count(), 27)
                self.assertTrue(Nota.objects.exists())
                self.assertTrue(Asistencia.objects.exists())
        for rut in Usuario.objects.values_list("rut", flat=True):
            validar_rut_chileno(rut)
        # Ningún correo apunta a un dominio real.
        self.assertFalse(Usuario.objects.exclude(email__endswith="@edugestor.test").exists())

    def test_misma_semilla_produce_mismos_datos(self):
        generar_datos("--alumnos-por-curso", "2")
        primero = self._resumen()
        generar_datos("--alumnos-por-curso", "2", "--limpiar")

        self.assertEqual(primero, self._resumen())

    def test_no_sobrescribe_datos_existentes_sin_limpiar(self):
        generar_datos("--alumnos-por-curso", "1")

        with self.assertRaises(CommandError):
            generar_datos()


class AislamientoInstitucionesTests(DjangoTestCase):
    """Pruebas de aislamiento entre instituciones (plan de pruebas, nivel 2)."""

    @classmethod
    def setUpTestData(cls):
        generar_datos("--alumnos-por-curso", "2")
        cls.chimbarongo = Institucion.objects.get(slug="instituto-chimbarongo")
        cls.maitenes = Institucion.objects.get(slug="escuela-los-maitenes")

    def modelos_institucionales(self):
        return [
            modelo for modelo in apps.get_app_config("colegio").get_models()
            if modelo is not Institucion and not modelo._meta.auto_created
        ]

    def test_todos_los_modelos_declaran_su_institucion(self):
        for modelo in self.modelos_institucionales():
            with self.subTest(modelo=modelo.__name__):
                campo = modelo._meta.get_field("institucion")
                self.assertEqual(campo.related_model, Institucion)
                # Solo el superusuario de plataforma puede no tener institución.
                self.assertEqual(campo.null, modelo is Usuario)

    def test_cada_modelo_filtra_por_la_institucion_activa(self):
        for modelo in self.modelos_institucionales():
            if modelo in (SolicitudPostulacion, InstrumentoIA, CorreccionPrueba):
                continue  # el comando no genera postulaciones ni documentos de IA
            total = modelo.objects.count()
            with self.subTest(modelo=modelo.__name__), institucion_activa(self.chimbarongo):
                visibles = modelo.objects.all()
                self.assertTrue(visibles.exists())
                self.assertLess(visibles.count(), total)
                self.assertFalse(visibles.exclude(institucion=self.chimbarongo).exists())

    def test_queryset_definido_sin_institucion_se_filtra_al_usarlo(self):
        # Como el queryset de un ModelChoiceField, creado al importar el módulo.
        queryset_global = Curso.objects.all()

        with institucion_activa(self.maitenes):
            self.assertEqual(
                set(queryset_global.all().values_list("institucion", flat=True)), {self.maitenes.pk}
            )
        self.assertEqual(queryset_global.count(), 27)

    def test_admin_no_ve_ni_edita_cursos_de_otra_institucion(self):
        self.client.force_login(Usuario.objects.get(username="chimbarongo.admin"))
        with institucion_activa(self.maitenes):
            curso_ajeno = Curso.objects.first()

        response = self.client.get(reverse("panel_admin_cursos"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            {curso.institucion_id for curso in response.context["cursos"]}, {self.chimbarongo.pk}
        )
        self.assertEqual(
            self.client.get(reverse("editar_curso", args=[curso_ajeno.pk])).status_code, 404
        )

    def test_admin_solo_lista_usuarios_de_su_institucion(self):
        self.client.force_login(Usuario.objects.get(username="maitenes.admin"))

        response = self.client.get(reverse("panel_admin_usuarios"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "maitenes.")
        self.assertNotContains(response, "chimbarongo.")
        self.assertNotContains(response, "almendro.")

    def test_registro_hereda_la_institucion_de_su_padre(self):
        with institucion_activa(self.maitenes):
            curso = Curso.objects.first()
        asignatura = Asignatura.objects.create(nombre_asignatura="Música", curso=curso)

        self.assertEqual(asignatura.institucion, self.maitenes)

    def test_no_se_pueden_mezclar_instituciones(self):
        with institucion_activa(self.chimbarongo):
            curso_chimbarongo = Curso.objects.first()
            asignatura_chimbarongo = Asignatura.objects.filter(curso=curso_chimbarongo).first()
        with institucion_activa(self.maitenes):
            docente_maitenes = Docente.objects.first()
            periodo_maitenes = PeriodoAcademico.objects.first()

        with self.assertRaises(InstitucionCruzadaError):
            CargaAcademica.objects.create(
                curso=curso_chimbarongo, asignatura=asignatura_chimbarongo,
                periodo=periodo_maitenes, docente=docente_maitenes,
            )
        with self.assertRaises(InstitucionCruzadaError):
            asignatura_chimbarongo.docentes.add(docente_maitenes)

    def test_misma_persona_puede_estar_en_dos_instituciones(self):
        rut = Usuario.objects.get(username="chimbarongo.docente1").rut

        self.assertEqual(
            set(Usuario.objects.filter(rut=rut).values_list("institucion__slug", flat=True)),
            {"instituto-chimbarongo", "escuela-los-maitenes"},
        )

    def test_rut_no_se_repite_dentro_de_una_institucion(self):
        existente = Usuario.objects.get(username="maitenes.alumno1")

        with self.assertRaises(IntegrityError):
            Usuario.objects.create(
                username="duplicado", rut=existente.rut, tipo_usuario="ALUMNO",
                institucion=self.maitenes,
            )

    def test_usuario_con_rol_requiere_institucion(self):
        with self.assertRaises(InstitucionCruzadaError):
            Usuario.objects.create(username="huerfano", rut="11.111.111-1", tipo_usuario="DOCENTE")

    def test_landing_y_postulacion_se_resuelven_por_slug(self):
        response = self.client.get(reverse("landing_cliente", args=["escuela-los-maitenes"]))
        self.assertEqual(response.context["colegio"], self.maitenes)
        self.assertContains(response, reverse("postulacion_alumno_cliente", args=["escuela-los-maitenes"]))
        self.assertEqual(self.client.get(reverse("landing_cliente", args=["no-existe"])).status_code, 404)
        self.assertEqual(
            self.client.get(reverse("postulacion_alumno_cliente", args=["escuela-el-almendro"])).status_code, 200
        )

    def test_usuario_con_sesion_ve_la_pagina_publica_de_otra_institucion(self):
        self.client.force_login(Usuario.objects.get(username="chimbarongo.admin"))

        response = self.client.get(reverse("landing_cliente", args=["escuela-los-maitenes"]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["colegio"], self.maitenes)

        # La página pública no cambia su institución: su panel sigue mostrando solo la suya.
        response = self.client.get(reverse("panel_admin_cursos"))
        self.assertEqual(
            {curso.institucion_id for curso in response.context["cursos"]}, {self.chimbarongo.pk}
        )


# ============================================================
# ASISTENTES DE IA (proveedor simulado: no se llama a la API)
# ============================================================
from unittest import mock

from django.test import override_settings

from .ia import asistentes
from .ia.proveedor import ErrorIA, _parsear_json
from .models import InstrumentoIA
from .templatetags.ia_extras import markdown_seguro


@override_settings(IA_PROVEEDOR="simulado")
class AsistenteIATestBase(TestCase):
    def setUp(self):
        self.periodo = PeriodoAcademico.objects.create(anio=2026, semestre=1)
        self.curso = Curso.objects.create(ciclo=Curso.CICLO_BASICA, nivel=4, seccion="A")
        self.otro_curso = Curso.objects.create(ciclo=Curso.CICLO_BASICA, nivel=5, seccion="A")
        self.asignatura = Asignatura.objects.create(nombre_asignatura="Matemática", curso=self.curso)
        self.asignatura_ajena = Asignatura.objects.create(nombre_asignatura="Historia", curso=self.otro_curso)

        self.usuario_docente = Usuario.objects.create_user(
            username="profe", password="x", rut="12.345.678-5", tipo_usuario="DOCENTE",
            first_name="Ana", last_name="Pérez", email="profe@edugestor.test")
        self.docente = self.usuario_docente.docente
        self.carga = CargaAcademica.objects.create(
            curso=self.curso, asignatura=self.asignatura, periodo=self.periodo, docente=self.docente)

        self.usuario_otro_docente = Usuario.objects.create_user(
            username="otroprofe", password="x", rut="9.876.543-3", tipo_usuario="DOCENTE",
            email="otro@edugestor.test")
        self.carga_ajena = CargaAcademica.objects.create(
            curso=self.otro_curso, asignatura=self.asignatura_ajena, periodo=self.periodo,
            docente=self.usuario_otro_docente.docente)

        self.usuario_alumno = Usuario.objects.create_user(
            username="alumna", password="x", rut="23.456.789-6", tipo_usuario="ALUMNO",
            first_name="Josefa", last_name="Quiroz")
        self.alumno = self.usuario_alumno.alumno
        Matricula.objects.create(periodo=self.periodo, alumno=self.alumno, curso=self.curso)

    def crear_prueba(self, cantidad=5):
        return self.client.post(reverse("ia_crear_prueba"), {
            "carga": self.carga.pk, "objetivo": "OA 7: fracciones", "tema": "fracciones",
            "cantidad": cantidad, "dificultad": "media",
        })

    def post_prueba(self, instrumento, accion, **cambios):
        datos = {"accion": accion, "titulo": instrumento.contenido["titulo"],
                 "instrucciones": instrumento.contenido["instrucciones"]}
        for i, pregunta in enumerate(instrumento.contenido["preguntas"]):
            datos[f"p{i}_enunciado"] = pregunta["enunciado"]
            datos[f"p{i}_correcta"] = str(pregunta["correcta"])
            datos[f"p{i}_explicacion"] = pregunta["explicacion"]
            for j, alternativa in enumerate(pregunta["alternativas"]):
                datos[f"p{i}_alt{j}"] = alternativa
        datos.update(cambios)
        return self.client.post(reverse("ia_instrumento", args=[instrumento.pk]), datos)


class AsistenteDocenteTests(AsistenteIATestBase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.usuario_docente)

    def test_menu_docente_muestra_asistente(self):
        response = self.client.get(reverse("panel_docente"))
        self.assertContains(response, reverse("asistente_docente"))
        self.assertEqual(self.client.get(reverse("asistente_docente")).status_code, 200)

    def test_crear_prueba_genera_borrador_editable(self):
        response = self.crear_prueba(cantidad=5)

        instrumento = InstrumentoIA.objects.get()
        self.assertRedirects(response, reverse("ia_instrumento", args=[instrumento.pk]))
        self.assertEqual(instrumento.tipo, InstrumentoIA.TIPO_PRUEBA)
        self.assertEqual(instrumento.estado, InstrumentoIA.ESTADO_BORRADOR)
        self.assertEqual(instrumento.institucion, self.institucion)
        self.assertEqual(len(instrumento.contenido["preguntas"]), 5)
        self.assertContains(self.client.get(response.url), 'name="p4_enunciado"')

    def test_solo_ofrece_las_cargas_del_docente(self):
        response = self.client.post(reverse("ia_crear_prueba"), {
            "carga": self.carga_ajena.pk, "tema": "x", "cantidad": 5, "dificultad": "media",
        })

        self.assertEqual(response.status_code, 200)
        self.assertIn("carga", response.context["form"].errors)
        self.assertFalse(InstrumentoIA.objects.exists())

    def test_aprobar_sin_cambios_registra_cero_por_ciento_corregido(self):
        self.crear_prueba()
        instrumento = InstrumentoIA.objects.get()

        self.post_prueba(instrumento, "aprobar")

        instrumento.refresh_from_db()
        self.assertEqual(instrumento.estado, InstrumentoIA.ESTADO_APROBADO)
        self.assertEqual(instrumento.porcentaje_corregido, 0)
        self.assertIsNotNone(instrumento.fecha_aprobacion)

    def test_aprobar_con_correcciones_mide_el_porcentaje_y_conserva_el_original(self):
        self.crear_prueba()
        instrumento = InstrumentoIA.objects.get()
        original = instrumento.contenido_ia

        self.post_prueba(instrumento, "aprobar", p0_enunciado="¿Qué fracción es equivalente a 1/2?",
                         p0_correcta="2", p1_eliminar="on")

        instrumento.refresh_from_db()
        self.assertGreater(instrumento.porcentaje_corregido, 0)
        self.assertEqual(instrumento.contenido_ia, original)
        self.assertEqual(len(instrumento.contenido["preguntas"]), 4)
        self.assertEqual(instrumento.contenido["preguntas"][0]["correcta"], 2)

    def test_guardar_no_aprueba_y_rechaza_campos_vacios(self):
        self.crear_prueba()
        instrumento = InstrumentoIA.objects.get()

        self.post_prueba(instrumento, "guardar", p0_enunciado="Nuevo enunciado")
        instrumento.refresh_from_db()
        self.assertEqual(instrumento.estado, InstrumentoIA.ESTADO_BORRADOR)
        self.assertEqual(instrumento.contenido["preguntas"][0]["enunciado"], "Nuevo enunciado")

        self.post_prueba(instrumento, "guardar", p0_alt1="")
        instrumento.refresh_from_db()
        self.assertEqual(instrumento.contenido["preguntas"][0]["alternativas"][1], "Alternativa B")

    def test_documento_aprobado_no_se_puede_editar(self):
        self.crear_prueba()
        instrumento = InstrumentoIA.objects.get()
        self.post_prueba(instrumento, "aprobar")

        self.post_prueba(instrumento, "guardar", p0_enunciado="Cambio tardío")

        instrumento.refresh_from_db()
        self.assertNotEqual(instrumento.contenido["preguntas"][0]["enunciado"], "Cambio tardío")
        self.assertContains(self.client.get(reverse("ia_instrumento", args=[instrumento.pk])), "Imprimir")

    def test_crear_y_aprobar_rubrica(self):
        self.client.post(reverse("ia_crear_rubrica"), {
            "carga": self.carga.pk, "actividad": "Disertación sobre el ciclo del agua", "niveles": 3,
        })
        instrumento = InstrumentoIA.objects.get(tipo=InstrumentoIA.TIPO_RUBRICA)
        contenido = instrumento.contenido
        self.assertEqual(len(contenido["niveles"]), 3)

        datos = {"accion": "aprobar", "titulo": contenido["titulo"], "descripcion": contenido["descripcion"]}
        for j, nivel in enumerate(contenido["niveles"]):
            datos[f"nivel_{j}"] = nivel
        for i, criterio in enumerate(contenido["criterios"]):
            datos[f"c{i}_criterio"] = criterio["criterio"]
            datos[f"c{i}_puntaje"] = criterio["puntaje_maximo"]
            for j, descriptor in enumerate(criterio["descriptores"]):
                datos[f"c{i}_d{j}"] = descriptor
        datos["c0_criterio"] = "Dominio del tema"
        self.client.post(reverse("ia_instrumento", args=[instrumento.pk]), datos)

        instrumento.refresh_from_db()
        self.assertEqual(instrumento.estado, InstrumentoIA.ESTADO_APROBADO)
        self.assertEqual(instrumento.contenido["criterios"][0]["criterio"], "Dominio del tema")
        self.assertGreater(instrumento.porcentaje_corregido, 0)

    def test_crear_material_y_verlo_como_html(self):
        self.client.post(reverse("ia_crear_material"), {
            "carga": self.carga.pk, "tema": "Los estados del agua", "tipo": "guia",
        })
        instrumento = InstrumentoIA.objects.get(tipo=InstrumentoIA.TIPO_MATERIAL)
        self.client.post(reverse("ia_instrumento", args=[instrumento.pk]), {
            "accion": "aprobar", "titulo": instrumento.titulo, "texto": instrumento.contenido["texto"],
        })

        response = self.client.get(reverse("ia_instrumento", args=[instrumento.pk]))
        self.assertContains(response, "<h2>Conceptos clave</h2>", html=True)

    def test_revisar_prueba(self):
        response = self.client.post(reverse("ia_revisar_prueba"), {
            "carga": self.carga.pk, "texto": "1. ¿Cuánto es 1/2 + 1/4?\na) 2/6 b) 3/4 c) 1/8 d) 2/4",
        })

        self.assertContains(response, "Observaciones")
        self.assertIsNotNone(response.context["revision"])

    def test_error_de_la_ia_se_muestra_y_no_crea_nada(self):
        with mock.patch("colegio.ia.asistentes.generar", side_effect=ErrorIA("Servicio caído")):
            response = self.crear_prueba()

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Servicio caído")
        self.assertFalse(InstrumentoIA.objects.exists())

    def test_otro_docente_no_ve_ni_elimina_el_instrumento(self):
        self.crear_prueba()
        instrumento = InstrumentoIA.objects.get()
        self.client.force_login(self.usuario_otro_docente)

        self.assertEqual(self.client.get(reverse("ia_instrumento", args=[instrumento.pk])).status_code, 404)
        self.assertEqual(
            self.client.post(reverse("ia_eliminar_instrumento", args=[instrumento.pk])).status_code, 404)
        self.assertTrue(InstrumentoIA.objects.filter(pk=instrumento.pk).exists())

    def test_eliminar_instrumento(self):
        self.crear_prueba()
        instrumento = InstrumentoIA.objects.get()

        response = self.client.post(reverse("ia_eliminar_instrumento", args=[instrumento.pk]))

        self.assertRedirects(response, reverse("asistente_docente"))
        self.assertFalse(InstrumentoIA.objects.exists())

    def test_alumno_no_accede_al_asistente_docente(self):
        self.client.force_login(self.usuario_alumno)

        response = self.client.get(reverse("ia_crear_prueba"))

        self.assertRedirects(response, reverse("panel_alumno"), fetch_redirect_response=False)


class TutorAlumnoTests(AsistenteIATestBase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.usuario_alumno)

    def test_menu_alumno_muestra_tutor(self):
        self.assertContains(self.client.get(reverse("panel_alumno")), reverse("tutor_alumno"))

    def test_conversacion_se_guarda_en_la_sesion(self):
        url = reverse("tutor_alumno")

        self.client.post(url, {"asignatura": self.asignatura.pk, "mensaje": "¿Qué es una fracción?"})
        response = self.client.get(url, {"asignatura": self.asignatura.pk})

        historial = response.context["historial"]
        self.assertEqual([m["rol"] for m in historial], ["usuario", "modelo"])
        self.assertContains(response, "¿Qué es una fracción?")

    def test_nueva_conversacion_borra_el_historial(self):
        url = reverse("tutor_alumno")
        self.client.post(url, {"asignatura": self.asignatura.pk, "mensaje": "Hola"})

        self.client.post(url, {"asignatura": self.asignatura.pk, "accion": "nueva"})

        self.assertEqual(self.client.get(url).context["historial"], [])

    def test_el_modelo_no_recibe_datos_personales_del_alumno(self):
        with mock.patch("colegio.ia.asistentes.generar", return_value="Pensemos juntos.") as generar:
            self.client.post(reverse("tutor_alumno"), {"asignatura": self.asignatura.pk, "mensaje": "Ayuda"})

        sistema, mensajes = generar.call_args.args
        enviado = sistema + " ".join(m["texto"] for m in mensajes)
        for dato in ("Josefa", "Quiroz", "23.456.789-6", "alumna"):
            self.assertNotIn(dato, enviado)
        self.assertIn("4° básico", sistema)
        self.assertIn("Matemática", sistema)

    def test_solo_puede_usar_asignaturas_de_su_curso(self):
        response = self.client.get(reverse("tutor_alumno"), {"asignatura": self.asignatura_ajena.pk})

        self.assertEqual(response.status_code, 404)

    def test_docente_no_accede_al_tutor(self):
        self.client.force_login(self.usuario_docente)

        response = self.client.get(reverse("tutor_alumno"))

        self.assertRedirects(response, reverse("panel_docente"), fetch_redirect_response=False)


class ProveedorIATests(DjangoTestCase):
    def test_parsea_json_con_bloque_de_codigo(self):
        self.assertEqual(_parsear_json('```json\n{"a": 1}\n```'), {"a": 1})

    def test_json_invalido_es_error_de_ia(self):
        with self.assertRaises(ErrorIA):
            _parsear_json("esto no es json")

    def test_prueba_mal_formada_es_error_de_ia(self):
        with self.assertRaises(ErrorIA):
            asistentes.validar_prueba({"preguntas": [{"enunciado": "x", "alternativas": ["a", "b"], "correcta": 0}]})

    def test_porcentaje_corregido(self):
        original = {"titulo": "T", "texto": "abcdefghij"}
        self.assertEqual(asistentes.porcentaje_corregido("MATERIAL", original, original), 0.0)
        self.assertGreater(asistentes.porcentaje_corregido("MATERIAL", original, {"titulo": "T", "texto": "xyz"}), 50)

    def test_markdown_de_la_ia_no_inyecta_html(self):
        html = markdown_seguro("**hola** <script>alert(1)</script>")

        self.assertIn("<strong>hola</strong>", html)
        self.assertNotIn("<script>", html)


# ============================================================
# CORRECCIÓN DE PRUEBAS RESPONDIDAS
# ============================================================
from django.core.files.uploadedfile import SimpleUploadedFile

from .models import CorreccionPrueba


def hoja(nombre="hoja.png", tipo="image/png"):
    return SimpleUploadedFile(nombre, b"\x89PNG\r\n\x1a\n imagen de prueba", content_type=tipo)


class CorregirPruebaTests(AsistenteIATestBase):
    """
    Con el proveedor simulado, la prueba de 5 preguntas tiene pauta B, C, D, A, B
    y la lectura simulada marca B, C, D, A y deja la 5 en blanco: 4/5 correctas.
    """

    def setUp(self):
        super().setUp()
        self.client.force_login(self.usuario_docente)
        self.crear_prueba(cantidad=5)
        self.prueba = InstrumentoIA.objects.get()
        self.post_prueba(self.prueba, "aprobar")
        self.prueba.refresh_from_db()
        self.url = reverse("ia_corregir_prueba", args=[self.prueba.pk])

    def calcular(self, respuestas, lecturas_ia=None, alumno=""):
        datos = {"accion": "calcular", "alumno": alumno, "leida_con_ia": "1" if lecturas_ia else "0"}
        for numero, valor in enumerate(respuestas, 1):
            datos[f"r{numero}"] = valor
        for numero, valor in enumerate(lecturas_ia or [], 1):
            datos[f"ia{numero}"] = valor
        return self.client.post(self.url, datos)

    def test_menu_lista_las_pruebas_aprobadas(self):
        response = self.client.get(reverse("ia_corregir"))

        self.assertContains(response, self.url)

    def test_no_se_corrige_un_borrador(self):
        self.crear_prueba(cantidad=3)
        borrador = InstrumentoIA.objects.filter(estado=InstrumentoIA.ESTADO_BORRADOR).get()

        response = self.client.get(reverse("ia_corregir_prueba", args=[borrador.pk]))

        self.assertRedirects(response, reverse("ia_instrumento", args=[borrador.pk]))

    def test_lee_la_hoja_y_destaca_preguntas_en_blanco(self):
        response = self.client.post(self.url, {"accion": "leer", "archivos": [hoja()]})

        self.assertEqual(response.context["paso"], "confirmar")
        self.assertEqual(response.context["por_revisar"], 1)
        estados = [lectura["estado"] for _, lectura in response.context["filas"]]
        self.assertEqual(estados, ["respondida"] * 4 + ["en_blanco"])
        self.assertContains(response, "En blanco")

    def test_a_la_ia_no_llega_el_alumno_ni_la_pauta(self):
        with mock.patch("colegio.ia.asistentes.generar", return_value={"respuestas": []}) as generar:
            self.client.post(self.url, {"accion": "leer", "alumno": self.alumno.pk, "archivos": [hoja()]})

        sistema, mensajes = generar.call_args.args
        enviado = sistema + mensajes[0]["texto"]
        for dato in ("Josefa", "Quiroz", "23.456.789-6", "Respuesta correcta", "Explicación"):
            self.assertNotIn(dato, enviado)
        self.assertEqual(mensajes[0]["archivos"][0][1], "image/png")

    def test_rechaza_archivos_que_no_son_imagen_ni_pdf(self):
        response = self.client.post(self.url, {"accion": "leer", "archivos": [hoja("notas.txt", "text/plain")]})

        self.assertEqual(response.context["paso"], "subir")
        self.assertContains(response, "no es una imagen")

    def test_pide_al_menos_un_archivo(self):
        response = self.client.post(self.url, {"accion": "leer"})

        self.assertContains(response, "Sube al menos una foto")

    def test_calcula_nota_con_la_pauta(self):
        response = self.calcular(["1", "2", "3", "0", ""], lecturas_ia=["1", "2", "3", "0", ""])

        correccion = CorreccionPrueba.objects.get()
        self.assertRedirects(response, reverse("ia_correccion", args=[correccion.pk]))
        self.assertEqual((correccion.correctas, correccion.total), (4, 5))
        self.assertEqual(float(correccion.nota), 5.5)
        self.assertEqual([r["estado"] for r in correccion.respuestas],
                         ["correcta"] * 4 + ["omitida"])
        self.assertTrue(correccion.leida_con_ia)
        self.assertEqual(correccion.ajustes_docente, 0)

    def test_cuenta_los_ajustes_del_docente_a_la_lectura(self):
        self.calcular(["1", "2", "0", "0", "1"], lecturas_ia=["1", "2", "3", "0", ""])

        correccion = CorreccionPrueba.objects.get()
        self.assertEqual(correccion.ajustes_docente, 2)
        self.assertEqual(correccion.respuestas[2]["estado"], "incorrecta")

    def test_ingreso_manual_sin_ia(self):
        response = self.client.get(self.url, {"manual": "1"})
        self.assertEqual(response.context["paso"], "confirmar")

        self.calcular(["", "", "", "", ""])

        correccion = CorreccionPrueba.objects.get()
        self.assertFalse(correccion.leida_con_ia)
        self.assertEqual(float(correccion.nota), 1.0)

    def test_registra_la_nota_en_el_libro(self):
        evaluacion = Evaluacion.objects.create(
            carga=self.carga, nombre_evaluacion="Prueba 1", tipo_evaluacion="Prueba",
            porcentaje=0, fecha="2026-05-10", numero_evaluacion=1)
        self.calcular(["1", "2", "3", "0", ""], alumno=self.alumno.pk)
        correccion = CorreccionPrueba.objects.get()

        self.client.post(reverse("ia_correccion", args=[correccion.pk]), {"evaluacion": evaluacion.pk})

        correccion.refresh_from_db()
        nota = Nota.objects.get(evaluacion=evaluacion, alumno=self.alumno)
        self.assertEqual(float(nota.valor_nota), 5.5)
        self.assertEqual(correccion.nota_registrada, nota)

    def test_no_acepta_alumno_de_otro_curso(self):
        otro = Usuario.objects.create_user(username="otro_alumno", password="x", rut="24.000.000-1",
                                           tipo_usuario="ALUMNO").alumno
        Matricula.objects.create(periodo=self.periodo, alumno=otro, curso=self.otro_curso)

        self.calcular(["1", "2", "3", "0", "1"], alumno=otro.pk)

        self.assertIsNone(CorreccionPrueba.objects.get().alumno)

    def test_otro_docente_no_ve_la_correccion(self):
        self.calcular(["1", "2", "3", "0", ""])
        correccion = CorreccionPrueba.objects.get()
        self.client.force_login(self.usuario_otro_docente)

        self.assertEqual(self.client.get(reverse("ia_correccion", args=[correccion.pk])).status_code, 404)
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_revisar_calidad_precarga_el_borrador(self):
        self.crear_prueba(cantidad=3)
        borrador = InstrumentoIA.objects.filter(estado=InstrumentoIA.ESTADO_BORRADOR).get()

        response = self.client.get(reverse("ia_revisar_prueba"), {"instrumento": borrador.pk})

        self.assertContains(response, "Respuesta correcta")
        self.assertEqual(response.context["form"].initial["carga"], self.carga)


class CalculoCorreccionTests(DjangoTestCase):
    def test_nota_chilena_con_60_por_ciento_de_exigencia(self):
        self.assertEqual(asistentes.nota_chilena(0, 10), 1.0)
        self.assertEqual(asistentes.nota_chilena(6, 10), 4.0)
        self.assertEqual(asistentes.nota_chilena(8, 10), 5.5)
        self.assertEqual(asistentes.nota_chilena(10, 10), 7.0)
        self.assertEqual(asistentes.nota_chilena(3, 10), 2.5)

    def test_normaliza_la_lectura_de_la_ia(self):
        lecturas = asistentes.validar_lectura({"respuestas": [
            {"pregunta": 1, "marcada": "b", "estado": "respondida"},
            {"pregunta": 2, "marcada": None, "estado": "respondida"},
            {"pregunta": 3, "marcada": None, "estado": "multiple"},
        ]}, cantidad=4)

        self.assertEqual([(l["marcada"], l["estado"]) for l in lecturas], [
            (1, "respondida"), (None, "ilegible"), (None, "multiple"), (None, "no_encontrada"),
        ])
