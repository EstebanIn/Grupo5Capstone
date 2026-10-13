"""
Genera un conjunto reproducible de datos sintéticos para desarrollo y pruebas.

Ningún dato corresponde a personas reales: nombres combinados al azar, RUT
generados con dígito verificador válido y correos bajo el dominio reservado
.test. Con la misma semilla se obtiene siempre el mismo estado de la base.

Genera tres instituciones (escuelas rurales) con el mismo esquema, para
demostrar y probar el aislamiento entre establecimientos. Una docente trabaja en
dos de ellas con el mismo RUT, caso real que la unicidad compuesta permite.

Uso:
    python manage.py generar_datos_sinteticos
    python manage.py generar_datos_sinteticos --limpiar --semilla 7
"""

import random
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.hashers import make_password
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from colegio.models import (
    AlumnoApoderado,
    Asignatura,
    Asistencia,
    CargaAcademica,
    Curso,
    Evaluacion,
    Institucion,
    Matricula,
    Nota,
    PeriodoAcademico,
    SolicitudPostulacion,
    Usuario,
)
from colegio.tenancy import institucion_activa

DOMINIO_CORREO = "edugestor.test"

NOMBRES = [
    "Agustín", "Benjamín", "Catalina", "Constanza", "Diego", "Emilia",
    "Florencia", "Gaspar", "Ignacia", "Joaquín", "Josefa", "Lucas",
    "Martina", "Matías", "Maximiliano", "Renata", "Sofía", "Tomás",
    "Valentina", "Vicente", "Amanda", "Bastián", "Isidora", "Cristóbal",
]
APELLIDOS = [
    "Araya", "Bravo", "Cáceres", "Contreras", "Díaz", "Espinoza",
    "Fuentes", "González", "Henríquez", "Jara", "Lagos", "Muñoz",
    "Navarro", "Orellana", "Pizarro", "Quiroz", "Reyes", "Rojas",
    "Salinas", "Tapia", "Valenzuela", "Vergara", "Zamorano", "Soto",
]
PARENTESCOS = ["Madre", "Padre", "Abuela", "Abuelo", "Tía", "Tío"]

ASIGNATURAS_KINDER = ["Lenguaje Verbal", "Pensamiento Matemático"]
ASIGNATURAS_BASICA = [
    "Lenguaje y Comunicación",
    "Matemática",
    "Ciencias Naturales",
    "Historia, Geografía y Ciencias Sociales",
]
TIPOS_EVALUACION = ["Prueba", "Trabajo", "Tarea"]

# (nombre, slug, prefijo de usuarios). La primera coincide con la landing demo existente.
INSTITUCIONES = [
    ("Instituto Chimbarongo", "instituto-chimbarongo", "chimbarongo"),
    ("Escuela Rural Los Maitenes", "escuela-los-maitenes", "maitenes"),
    ("Escuela Rural El Almendro", "escuela-el-almendro", "almendro"),
]


def calcular_dv(cuerpo):
    suma, multiplicador = 0, 2
    for digito in reversed(str(cuerpo)):
        suma += int(digito) * multiplicador
        multiplicador = 2 if multiplicador == 7 else multiplicador + 1
    resto = 11 - (suma % 11)
    return {11: "0", 10: "K"}.get(resto, str(resto))


def formatear_rut(cuerpo):
    return f"{cuerpo:,}".replace(",", ".") + f"-{calcular_dv(cuerpo)}"


class Command(BaseCommand):
    help = "Genera datos sintéticos reproducibles (sin datos reales de personas)."

    def add_arguments(self, parser):
        parser.add_argument("--semilla", type=int, default=42,
                            help="Semilla aleatoria; la misma semilla produce los mismos datos.")
        parser.add_argument("--instituciones", type=int, default=len(INSTITUCIONES),
                            choices=range(1, len(INSTITUCIONES) + 1))
        parser.add_argument("--alumnos-por-curso", type=int, default=8)
        parser.add_argument("--password", default="EduGestor@123",
                            help="Contraseña común para todos los usuarios generados.")
        parser.add_argument("--anio", type=int, default=2026)
        parser.add_argument("--limpiar", action="store_true",
                            help="Elimina datos académicos, instituciones y usuarios no superusuarios antes de generar.")

    def handle(self, *args, **opciones):
        self.rng = random.Random(opciones["semilla"])
        self.password = opciones["password"]
        # Se calcula el hash una sola vez: hacerlo por usuario domina el tiempo de ejecución.
        self.password_hash = make_password(self.password)

        hay_datos = Usuario.objects.filter(is_superuser=False).exists() or Curso.objects.exists()
        if hay_datos and not opciones["limpiar"]:
            raise CommandError(
                "La base ya tiene datos. Usa --limpiar para reemplazarlos por los datos sintéticos."
            )

        with transaction.atomic():
            if opciones["limpiar"]:
                self._limpiar()
            self.ruts_usados = set(Usuario.objects.values_list("rut", flat=True))

            resumenes = []
            docente_compartida = None
            for nombre, slug, prefijo in INSTITUCIONES[:opciones["instituciones"]]:
                institucion = Institucion.objects.create(nombre=nombre, slug=slug)
                with institucion_activa(institucion):
                    resumen, docente_compartida = self._generar(
                        institucion, prefijo, opciones["anio"],
                        opciones["alumnos_por_curso"], docente_compartida,
                    )
                resumenes.append(resumen)

        self.stdout.write(self.style.SUCCESS("Datos sintéticos generados:"))
        for resumen in resumenes:
            self.stdout.write(f"  {resumen.pop('institucion')} (usuarios {resumen.pop('prefijo')}.*)")
            self.stdout.write("    " + ", ".join(f"{clave}: {valor}" for clave, valor in resumen.items()))
        self.stdout.write(
            "Usuarios: <prefijo>.admin, <prefijo>.docente1..5, <prefijo>.alumnoN, <prefijo>.apoderadoN "
            f"(contraseña: {self.password})"
        )

    # ------------------------------------------------------------------
    def _limpiar(self):
        for modelo in (Nota, Asistencia, Evaluacion, CargaAcademica, Matricula,
                       AlumnoApoderado, SolicitudPostulacion, Asignatura, Curso,
                       PeriodoAcademico):
            modelo.objects.all().delete()
        # Los perfiles Alumno/Docente/Apoderado caen en cascada con el usuario.
        Usuario.objects.filter(is_superuser=False).delete()
        Institucion.objects.filter(usuarios__isnull=True).delete()

    def _nuevo_rut(self, minimo, maximo):
        while True:
            rut = formatear_rut(self.rng.randint(minimo, maximo))
            if rut not in self.ruts_usados:
                self.ruts_usados.add(rut)
                return rut

    def _nombre(self):
        return self.rng.choice(NOMBRES), self.rng.choice(APELLIDOS)

    def _crear_usuario(self, username, tipo, nombre, apellido, rut_rango, rut=None, **extra):
        username = f"{self.prefijo}.{username}"
        return Usuario.objects.create(
            username=username,
            password=self.password_hash,
            tipo_usuario=tipo,
            first_name=nombre,
            last_name=apellido,
            email=f"{username}@{DOMINIO_CORREO}",
            rut=rut or self._nuevo_rut(*rut_rango),
            **extra,
        )

    # ------------------------------------------------------------------
    def _generar(self, institucion, prefijo, anio, alumnos_por_curso, docente_compartida):
        rng = self.rng
        self.prefijo = prefijo

        self._crear_usuario("admin", "ADMIN", "Administración", institucion.nombre,
                            (9_000_000, 11_000_000), is_staff=True)

        periodo = PeriodoAcademico.objects.create(anio=anio, semestre=1)

        # Escuela rural: Kinder y 1° a 8° básico, una sección por nivel.
        cursos = [Curso.objects.create(ciclo=Curso.CICLO_KINDER, nivel=1, seccion="A")]
        cursos += [
            Curso.objects.create(ciclo=Curso.CICLO_BASICA, nivel=nivel, seccion="A")
            for nivel in range(1, 9)
        ]

        # Cuerpo docente reducido: cada docente atiende varios cursos (multigrado).
        # docente1 de la segunda institución es la misma persona que docente1 de la primera.
        docentes = []
        for i in range(1, 6):
            if i == 1 and docente_compartida:
                nombre, apellido, rut = docente_compartida
            else:
                (nombre, apellido), rut = self._nombre(), None
            usuario = self._crear_usuario(f"docente{i}", "DOCENTE", nombre, apellido,
                                          (10_000_000, 19_000_000), rut=rut)
            docente = usuario.docente
            docente.telefono = f"+569{rng.randint(10_000_000, 99_999_999)}"
            docente.save(update_fields=["telefono"])
            docentes.append(docente)
        if docente_compartida is None:
            primera = docentes[0].usuario
            docente_compartida = (primera.first_name, primera.last_name, primera.rut)
        else:
            docente_compartida = ()  # solo se comparte entre las dos primeras instituciones

        cargas = []
        for indice, curso in enumerate(cursos):
            curso.profesor_jefe = docentes[indice % len(docentes)]
            curso.save(update_fields=["profesor_jefe"])
            nombres = ASIGNATURAS_KINDER if curso.ciclo == Curso.CICLO_KINDER else ASIGNATURAS_BASICA
            for posicion, nombre_asignatura in enumerate(nombres):
                asignatura = Asignatura.objects.create(nombre_asignatura=nombre_asignatura, curso=curso)
                docente = docentes[(indice + posicion) % len(docentes)]
                asignatura.docentes.add(docente)
                cargas.append(CargaAcademica.objects.create(
                    curso=curso, asignatura=asignatura, periodo=periodo, docente=docente,
                ))

        # Alumnos con su apoderado; algunos hermanos comparten apoderado.
        alumnos_por_curso_id = {}
        apoderados = []
        n_alumno = 0
        for curso in cursos:
            edad = 5 if curso.ciclo == Curso.CICLO_KINDER else 5 + curso.nivel
            for _ in range(alumnos_por_curso):
                n_alumno += 1
                nombre, apellido = self._nombre()
                usuario = self._crear_usuario(f"alumno{n_alumno}", "ALUMNO", nombre, apellido,
                                              (22_000_000, 27_000_000))
                alumno = usuario.alumno
                alumno.fecha_nacimiento = date(anio - edad, rng.randint(1, 12), rng.randint(1, 28))
                alumno.genero = rng.choice(["Femenino", "Masculino"])
                alumno.estado_alumno = "Activo"
                alumno.save()

                if apoderados and rng.random() < 0.15:
                    apoderado = rng.choice(apoderados)
                else:
                    nombre_ap, _ = self._nombre()
                    usuario_ap = self._crear_usuario(
                        f"apoderado{len(apoderados) + 1}", "APODERADO", nombre_ap, apellido,
                        (8_000_000, 18_000_000),
                    )
                    apoderado = usuario_ap.apoderado
                    apoderado.telefono = f"+569{rng.randint(10_000_000, 99_999_999)}"
                    apoderado.direccion = f"Camino rural {rng.randint(1, 60)} km {rng.randint(1, 30)}"
                    apoderado.save(update_fields=["telefono", "direccion"])
                    apoderados.append(apoderado)

                AlumnoApoderado.objects.create(
                    alumno=alumno, apoderado=apoderado,
                    parentesco=rng.choice(PARENTESCOS), is_principal=True,
                )
                matricula = Matricula.objects.create(periodo=periodo, alumno=alumno, curso=curso)
                matricula.apoderados.add(apoderado)
                alumnos_por_curso_id.setdefault(curso.id, []).append(alumno)

        # Rendimiento base por alumno para que las notas sean coherentes entre asignaturas.
        habilidad = {
            alumno.id: rng.gauss(5.3, 0.6)
            for lista in alumnos_por_curso_id.values() for alumno in lista
        }

        # bulk_create no pasa por save(): la institución se asigna explícitamente.
        inicio = date(anio, 3, 4)
        notas, asistencias, total_evaluaciones = [], [], 0
        for posicion_carga, carga in enumerate(cargas):
            alumnos = alumnos_por_curso_id[carga.curso_id]

            for numero in range(1, 4):
                evaluacion = Evaluacion.objects.create(
                    carga=carga,
                    nombre_evaluacion=f"{TIPOS_EVALUACION[numero - 1]} {numero}",
                    tipo_evaluacion=TIPOS_EVALUACION[numero - 1],
                    porcentaje=0,
                    fecha=inicio + timedelta(weeks=5 * numero),
                    numero_evaluacion=numero,
                )
                total_evaluaciones += 1
                for alumno in alumnos:
                    valor = min(7.0, max(1.0, rng.gauss(habilidad[alumno.id], 0.5)))
                    notas.append(Nota(
                        institucion=institucion, evaluacion=evaluacion, alumno=alumno,
                        valor_nota=Decimal(f"{valor:.1f}"),
                    ))

            # Una clase semanal por asignatura durante 12 semanas.
            for semana in range(12):
                fecha = inicio + timedelta(weeks=semana, days=posicion_carga % 5)
                for alumno in alumnos:
                    azar = rng.random()
                    estado = "Presente" if azar < 0.88 else ("Ausente" if azar < 0.96 else "Justificado")
                    asistencias.append(Asistencia(
                        institucion=institucion, alumno=alumno, carga=carga,
                        fecha=fecha, estado_asistencia=estado,
                    ))

        Nota.objects.bulk_create(notas)
        Asistencia.objects.bulk_create(asistencias)

        resumen = {
            "institucion": institucion.nombre,
            "prefijo": prefijo,
            "cursos": len(cursos),
            "docentes": len(docentes),
            "cargas": len(cargas),
            "alumnos": n_alumno,
            "apoderados": len(apoderados),
            "evaluaciones": total_evaluaciones,
            "notas": len(notas),
            "asistencia": len(asistencias),
        }
        return resumen, docente_compartida
