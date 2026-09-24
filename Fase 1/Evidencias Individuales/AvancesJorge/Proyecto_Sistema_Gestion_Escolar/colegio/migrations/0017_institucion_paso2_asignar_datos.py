"""
Paso 2 de 3: asigna todos los datos existentes a una institución.

La base previa al cambio pertenece a un único establecimiento, así que todo
queda bajo una institución por defecto. Los superusuarios sin rol quedan sin
institución: son administradores de plataforma.
"""

from django.db import migrations

MODELOS_INSTITUCIONALES = [
    "Alumno", "Docente", "Apoderado", "AlumnoApoderado", "SolicitudPostulacion",
    "Curso", "Asignatura", "PeriodoAcademico", "Matricula", "CargaAcademica",
    "Evaluacion", "Nota", "Asistencia",
]


def asignar_institucion_por_defecto(apps, schema_editor):
    Institucion = apps.get_model("colegio", "Institucion")
    Usuario = apps.get_model("colegio", "Usuario")

    hay_datos = Usuario.objects.exclude(tipo_usuario="").exists() or any(
        apps.get_model("colegio", nombre).objects.exists()
        for nombre in MODELOS_INSTITUCIONALES
    )
    if not hay_datos:
        return

    institucion, _ = Institucion.objects.get_or_create(
        slug="instituto-chimbarongo",
        defaults={"nombre": "Instituto Chimbarongo"},
    )
    Usuario.objects.exclude(tipo_usuario="").filter(institucion__isnull=True).update(
        institucion=institucion
    )
    for nombre in MODELOS_INSTITUCIONALES:
        apps.get_model("colegio", nombre).objects.filter(institucion__isnull=True).update(
            institucion=institucion
        )


class Migration(migrations.Migration):

    dependencies = [
        ("colegio", "0016_institucion_paso1_campos_opcionales"),
    ]

    operations = [
        migrations.RunPython(asignar_institucion_por_defecto, migrations.RunPython.noop),
    ]
