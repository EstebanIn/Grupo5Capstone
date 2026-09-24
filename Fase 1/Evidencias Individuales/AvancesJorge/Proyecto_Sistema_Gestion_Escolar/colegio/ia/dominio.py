"""
Interfaz interna de dominio para los asistentes.

Los asistentes nunca consultan la base de datos: reciben solo lo que estas
funciones entregan. Aquí se decide qué datos puede ver la IA, y la regla es
que no salga ningún dato personal (nombres, RUT, notas, asistencia) de
alumnos. Las consultas quedan además acotadas a la institución activa por los
managers de los modelos.
"""

from ..models import Alumno, Asignatura, CargaAcademica, Curso, Matricula


def cargas_docente(docente):
    return (
        CargaAcademica.objects.filter(docente=docente)
        .select_related("curso", "asignatura", "periodo")
        .order_by("curso__ciclo", "curso__nivel", "asignatura__nombre_asignatura")
    )


def contexto_carga(carga):
    """Curso y asignatura, sin datos de alumnos."""
    return {
        "curso": str(carga.curso),
        "nivel": _describir_nivel(carga.curso),
        "asignatura": carga.asignatura.nombre_asignatura,
    }


def curso_actual_alumno(alumno):
    matricula = (
        Matricula.objects.filter(alumno=alumno)
        .select_related("curso", "periodo")
        .order_by("-periodo__anio", "-periodo__semestre")
        .first()
    )
    return matricula.curso if matricula else None


def asignaturas_alumno(alumno):
    curso = curso_actual_alumno(alumno)
    if curso is None:
        return Asignatura.objects.none()
    return Asignatura.objects.filter(curso=curso, estado_asignatura=True).order_by("nombre_asignatura")


def contexto_tutor(asignatura):
    """Lo único que el tutor sabe del alumno: su nivel y la asignatura."""
    return {
        "nivel": _describir_nivel(asignatura.curso),
        "asignatura": asignatura.nombre_asignatura,
    }


def _describir_nivel(curso):
    if curso.ciclo == Curso.CICLO_KINDER:
        return "Kinder (5 a 6 años)"
    ciclo = "básico" if curso.ciclo == Curso.CICLO_BASICA else "medio"
    edad = curso.nivel + 5 if curso.ciclo == Curso.CICLO_BASICA else curso.nivel + 13
    return f"{curso.nivel}° {ciclo} (alrededor de {edad} años)"


def alumnos_de_carga(carga):
    """Alumnos matriculados en el curso de la carga, en su período."""
    return (
        Alumno.objects.filter(matricula__curso=carga.curso, matricula__periodo=carga.periodo)
        .select_related("usuario")
        .order_by("apellido_alumno", "nombre_alumno")
        .distinct()
    )
