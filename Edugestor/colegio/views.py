from django.contrib import messages
from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.shortcuts import redirect, render, get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.utils.crypto import get_random_string
from django.shortcuts import render
from django.db.models import Avg, Count, Q
from django.http import JsonResponse
import pandas as pd

from .forms import (
    AlumnoAdminForm,
    DocenteAdminForm,
    ApoderadoAdminForm,
    MatriculaForm,
    MatriculaAdminForm,
    MatriculaAdminFormEdit,
    CursoForm,
    AsignaturaForm,
    DocenteForm,
    RegistroAlumnoApoderadoForm,
    PostulacionAlumnoForm,
)
from .models import (
    Alumno,
    Apoderado,
    Docente,
    AlumnoApoderado,
    Matricula,
    Nota,
    Curso,
    Asignatura,
    PeriodoAcademico,
    CargaAcademica,
    Evaluacion,
    Asistencia,
    SolicitudPostulacion, 
)

Usuario = get_user_model()


# ============================================================
# FUNCIONES AUXILIARES
# ============================================================

def generar_username_desde_rut(rut):
    """
    Genera un username limpio a partir del RUT.
    Ejemplo: 12.345.678-9 → 123456789
    """
    return rut.replace(".", "").replace("-", "").lower()


def crear_usuario_con_rol(*, rut, tipo_usuario, first_name, last_name, email=""):
    """
    Crea un Usuario con contraseña hasheada y retorna:
    - usuario creado
    - username generado
    - password temporal
    """
    username = generar_username_desde_rut(rut)
    password_temporal = get_random_string(8)

    usuario = Usuario.objects.create_user(
        username=username,
        password=password_temporal,
        rut=rut,
        tipo_usuario=tipo_usuario,
        first_name=first_name,
        last_name=last_name,
        email=email,
    )

    return usuario, username, password_temporal


def redireccionar_por_rol(usuario):
    """
    Redirige al usuario autenticado según su tipo_usuario.
    Centraliza la lógica de roles para no repetir condicionales.
    """
    roles = {
        "ADMIN": "panel_admin",
        "DOCENTE": "panel_docente",
        "ALUMNO": "panel_alumno",
        "APODERADO": "panel_apoderado",
    }
    destino = roles.get(usuario.tipo_usuario, "inicio")
    return redirect(destino)


def es_admin(user):
    """Verifica si el usuario autenticado es administrador."""
    return user.is_authenticated and user.tipo_usuario == "ADMIN"


def obtener_periodo_academico_actual():
    """Obtiene el periodo mas reciente para crear cargas academicas."""
    periodo = PeriodoAcademico.objects.order_by("-anio", "-semestre").first()
    if periodo:
        return periodo

    hoy = timezone.localdate()
    semestre = 1 if hoy.month <= 6 else 2
    periodo, _ = PeriodoAcademico.objects.get_or_create(
        anio=hoy.year,
        semestre=semestre,
    )
    return periodo


def sincronizar_cargas_asignatura(asignatura, periodo=None):
    """
    Crea las cargas academicas faltantes para los docentes de una asignatura.
    El panel docente se alimenta de CargaAcademica, no directamente del M2M
    Asignatura.docentes.
    """
    periodo = periodo or obtener_periodo_academico_actual()
    if not periodo:
        return 0

    creadas = 0
    for docente in asignatura.docentes.all():
        _, creada = CargaAcademica.objects.get_or_create(
            curso=asignatura.curso,
            asignatura=asignatura,
            periodo=periodo,
            docente=docente,
        )
        if creada:
            creadas += 1

    return creadas


def sincronizar_docentes_removidos_asignatura(asignatura, docentes_seleccionados):
    """
    Quita o transfiere cargas de docentes que fueron desmarcados de una asignatura.
    Si una carga no tiene historial, se elimina. Si tiene historial, se transfiere
    solo cuando hay un unico docente seleccionado como reemplazo.
    """
    docentes_seleccionados = list(docentes_seleccionados)
    docentes_ids = {docente.id for docente in docentes_seleccionados}
    docente_reemplazo = docentes_seleccionados[0] if len(docentes_seleccionados) == 1 else None
    errores = []

    cargas_removidas = CargaAcademica.objects.filter(
        asignatura=asignatura
    ).exclude(
        docente_id__in=docentes_ids
    ).select_related("docente", "curso", "periodo")

    for carga in cargas_removidas:
        tiene_historial = (
            Evaluacion.objects.filter(carga=carga).exists()
            or Asistencia.objects.filter(carga=carga).exists()
        )

        if not tiene_historial:
            carga.delete()
            continue

        if not docente_reemplazo:
            errores.append(
                f"{carga.docente} tiene historial en {carga.asignatura.nombre_asignatura} ({carga.curso}). "
                "Selecciona exactamente un docente reemplazante para conservarlo."
            )
            continue

        carga_duplicada = CargaAcademica.objects.filter(
            curso=carga.curso,
            asignatura=carga.asignatura,
            periodo=carga.periodo,
            docente=docente_reemplazo,
        ).exclude(pk=carga.pk).exists()

        if carga_duplicada:
            errores.append(
                f"No se puede transferir {carga.asignatura.nombre_asignatura} ({carga.curso}) a {docente_reemplazo}: "
                "ese docente ya tiene la misma carga."
            )
            continue

        carga.docente = docente_reemplazo
        carga.save(update_fields=["docente"])

    if errores:
        raise ValueError(" ".join(errores))


def asegurar_cargas_docente(docente):
    """Repara asignaciones antiguas que aun no tienen carga academica."""
    periodo = obtener_periodo_academico_actual()
    if not periodo:
        return 0

    creadas = 0
    asignaturas = Asignatura.objects.filter(docentes=docente).select_related("curso")
    for asignatura in asignaturas:
        creadas += sincronizar_cargas_asignatura(asignatura, periodo)

    return creadas
# ============================================================
# HELPERS ALUMNO / APODERADO / POSTULACIONES
# ============================================================

PASSWORD_INICIAL_ALUMNO = "EduGestor@123"


def crear_alumno_apoderado_desde_data(data):
    """
    Crea usuarios, perfiles y relación Alumno-Apoderado.

    Importante:
    No usa Alumno.objects.create() ni Apoderado.objects.create(),
    porque la señal post_save ya crea esos perfiles al crear Usuario.
    """

    # 1. Crear Usuario del Apoderado.
    usuario_apoderado = Usuario.objects.create_user(
        username=data["username_apoderado"],
        password=PASSWORD_INICIAL_ALUMNO,
        rut=data["rut_apoderado"],
        tipo_usuario="APODERADO",
        first_name=data["nombre_apoderado"],
        last_name=data["apellido_apoderado"],
        email=data["email_apoderado"],
    )

    # 2. Recuperar y actualizar perfil Apoderado autogenerado.
    apoderado = Apoderado.objects.select_for_update().get(
        usuario=usuario_apoderado
    )
    apoderado.nombre_apoderado = data["nombre_apoderado"]
    apoderado.apellido_apoderado = data["apellido_apoderado"]
    apoderado.direccion = data["direccion"]
    apoderado.telefono = data["telefono"]
    apoderado.email = data["email_apoderado"]
    apoderado.save()

    # 3. Crear Usuario del Alumno.
    usuario_alumno = Usuario.objects.create_user(
        username=data["username_alumno"],
        password=PASSWORD_INICIAL_ALUMNO,
        rut=data["rut_alumno"],
        tipo_usuario="ALUMNO",
        first_name=data["nombre_alumno"],
        last_name=data["apellido_alumno"],
        email="",
    )

    # 4. Recuperar y actualizar perfil Alumno autogenerado.
    alumno = Alumno.objects.select_for_update().get(
        usuario=usuario_alumno
    )
    alumno.nombre_alumno = data["nombre_alumno"]
    alumno.apellido_alumno = data["apellido_alumno"]
    alumno.fecha_nacimiento = data["fecha_nacimiento"]
    alumno.genero = data["genero"]
    alumno.estado_alumno = "Activo"
    alumno.save()

    # 5. Crear relación Alumno-Apoderado.
    AlumnoApoderado.objects.create(
        alumno=alumno,
        apoderado=apoderado,
        parentesco=data["parentesco"],
        is_principal=data["is_principal"],
    )

    return {
        "usuario_alumno": usuario_alumno,
        "usuario_apoderado": usuario_apoderado,
        "alumno": alumno,
        "apoderado": apoderado,
    }


def data_desde_solicitud_postulacion(solicitud):
    """
    Convierte una SolicitudPostulacion en data compatible
    con crear_alumno_apoderado_desde_data().
    """

    return {
        "rut_alumno": solicitud.rut_alumno,
        "username_alumno": solicitud.rut_alumno_normalizado,
        "nombre_alumno": solicitud.nombre_alumno,
        "apellido_alumno": solicitud.apellido_alumno,
        "fecha_nacimiento": solicitud.fecha_nacimiento,
        "genero": solicitud.genero,

        "rut_apoderado": solicitud.rut_apoderado,
        "username_apoderado": solicitud.rut_apoderado_normalizado,
        "nombre_apoderado": solicitud.nombre_apoderado,
        "apellido_apoderado": solicitud.apellido_apoderado,
        "direccion": solicitud.direccion or "",
        "telefono": solicitud.telefono or "",
        "email_apoderado": solicitud.email_apoderado,

        "parentesco": solicitud.parentesco,
        "is_principal": solicitud.is_principal,
    }

# ============================================================
# PÁGINAS PÚBLICAS
# ============================================================

def inicio(request):
    """Página principal pública del sistema EduGestor."""
    return render(request, "colegio/home.html")


def home(request):
    """Alias para mantener compatibilidad con URLs que usen 'home'."""
    return render(request, "colegio/home.html")

def postulacion_alumno(request, slug_colegio=None):
    """
    Formulario público para que padres/apoderados postulen a un alumno.

    Esta vista NO crea usuarios.
    Solo guarda una SolicitudPostulacion en estado PENDIENTE.
    """
    # La postulación siempre es a un establecimiento concreto (resuelto por
    # InstitucionMiddleware desde el slug de la URL).
    if request.institucion is None:
        return redirect("inicio")
    slug_colegio = request.institucion.slug

    if request.method == "POST":
        form = PostulacionAlumnoForm(request.POST)

        if form.is_valid():
            data = form.cleaned_data

            SolicitudPostulacion.objects.create(
                rut_alumno=data["rut_alumno"],
                rut_alumno_normalizado=data["username_alumno"],
                nombre_alumno=data["nombre_alumno"],
                apellido_alumno=data["apellido_alumno"],
                fecha_nacimiento=data["fecha_nacimiento"],
                genero=data["genero"],

                ciclo_postulacion=data["ciclo_postulacion"],
                nivel_postulacion=data["nivel_postulacion"],

                rut_apoderado=data["rut_apoderado"],
                rut_apoderado_normalizado=data["username_apoderado"],
                nombre_apoderado=data["nombre_apoderado"],
                apellido_apoderado=data["apellido_apoderado"],
                direccion=data["direccion"],
                telefono=data["telefono"],
                email_apoderado=data["email_apoderado"],

                parentesco=data["parentesco"],
                is_principal=data["is_principal"],
                estado="PENDIENTE",
            )

            return redirect("postulacion_exitosa", slug_colegio=slug_colegio)

    else:
        form = PostulacionAlumnoForm()

    return render(request, "colegio/postulacion_alumno.html", {
        "form": form,
        "slug_colegio": slug_colegio,
    })

def postulacion_exitosa(request, slug_colegio):
    context = {
        'slug_colegio': slug_colegio
    }
    """
    Página pública de confirmación después de enviar la postulación.
    """
    return render(request, "colegio/postulacion_exitosa.html", context)

# ============================================================
# LOGIN / LOGOUT
# ============================================================

def login_view(request):
    """
    Login usando el sistema de autenticación de Django.
    Redirige automáticamente según el rol del usuario.
    """
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")

        usuario = authenticate(request, username=username, password=password)

        if usuario is not None:
            login(request, usuario)
            return redireccionar_por_rol(usuario)

        return render(request, "colegio/login.html", {
            "error": "Usuario o contraseña incorrectos."
        })

    return render(request, "colegio/login.html")


def logout_view(request):
    """Cierra la sesión del usuario actual."""
    logout(request)
    return redirect("login")


# ============================================================
# PANEL ADMINISTRADOR
# ============================================================

@login_required
def panel_admin(request):
    """Panel principal con métricas globales del sistema."""
    if not es_admin(request.user):
        return redireccionar_por_rol(request.user)

    return render(request, "colegio/panel_admin.html", {
        "total_usuarios": Usuario.objects.count(),
        "total_alumnos": Alumno.objects.count(),
        "total_apoderados": Apoderado.objects.count(),
        "total_docentes": Docente.objects.count(),
        "total_cursos": Curso.objects.count(),
        "actividades": [
            {"usuario": "Administrador", "accion": "Accedió al sistema", "fecha": "Hoy", "estado": "Completado"}
        ],
    })


@login_required
def panel_admin_usuarios(request):
    """Lista todos los usuarios del sistema."""
    if not es_admin(request.user):
        return redireccionar_por_rol(request.user)

    rol_filtro = request.GET.get("rol", "").lower()
    roles_validos = {
        "admin": "ADMIN",
        "docente": "DOCENTE",
        "alumno": "ALUMNO",
        "apoderado": "APODERADO",
    }

    usuarios = Usuario.objects.all()
    if rol_filtro in roles_validos:
        usuarios = usuarios.filter(tipo_usuario=roles_validos[rol_filtro])
    else:
        rol_filtro = ""

    return render(request, "colegio/panel_admin_usuarios.html", {
        "usuarios": usuarios.order_by("username"),
        "rol_filtro": rol_filtro,
    })


@login_required
def panel_admin_cursos(request):
    """Lista todos los cursos del sistema."""
    if not es_admin(request.user):
        return redireccionar_por_rol(request.user)

    cursos = Curso.objects.all().order_by("ciclo", "nivel", "seccion")
    curso_id = request.GET.get("curso_id")
    curso_seleccionado = None
    matriculas_curso = []
    alumnos_curso_detalle = []

    if curso_id:
        curso_seleccionado = get_object_or_404(Curso, pk=curso_id)
        # Filtra siempre por el id exacto que viene desde el curso clickeado.
        matriculas_curso = list(Matricula.objects.filter(
            curso_id=curso_seleccionado.pk
        ).select_related(
            "alumno",
            "alumno__usuario",
            "periodo",
        ).order_by("alumno__apellido_alumno", "alumno__nombre_alumno"))
        alumnos_ids = [matricula.alumno_id for matricula in matriculas_curso]
        asignaturas_curso = list(
            Asignatura.objects.filter(
                curso=curso_seleccionado,
                estado_asignatura=True,
            ).order_by("nombre_asignatura")
        )
        evaluaciones_curso = Evaluacion.objects.filter(
            carga__curso=curso_seleccionado,
            carga__asignatura__in=asignaturas_curso,
        ).select_related(
            "carga",
            "carga__asignatura",
        ).order_by(
            "carga__asignatura__nombre_asignatura",
            "numero_evaluacion",
            "fecha",
        )
        evaluaciones_por_asignatura = {
            asignatura.id: []
            for asignatura in asignaturas_curso
        }
        for evaluacion in evaluaciones_curso:
            evaluaciones_por_asignatura.setdefault(evaluacion.carga.asignatura_id, []).append(evaluacion)

        notas_curso = Nota.objects.filter(
            alumno_id__in=alumnos_ids,
            evaluacion__carga__curso=curso_seleccionado,
        ).select_related(
            "evaluacion",
            "evaluacion__carga",
            "evaluacion__carga__asignatura",
        )

        for matricula in matriculas_curso:
            alumno = matricula.alumno
            notas_alumno = notas_curso.filter(alumno=alumno)
            promedio_alumno = notas_alumno.aggregate(promedio=Avg("valor_nota"))["promedio"] or 0
            notas_por_evaluacion = {
                nota.evaluacion_id: nota
                for nota in notas_alumno
            }

            asignaturas_detalle = []
            for asignatura in asignaturas_curso:
                evaluaciones_detalle = []
                notas_asignatura = []

                for evaluacion in evaluaciones_por_asignatura.get(asignatura.id, []):
                    nota = notas_por_evaluacion.get(evaluacion.id)
                    if nota:
                        notas_asignatura.append(nota.valor_nota)

                    evaluaciones_detalle.append({
                        "evaluacion": evaluacion,
                        "nota": nota,
                    })

                promedio_asignatura = (
                    round(float(sum(notas_asignatura) / len(notas_asignatura)), 1)
                    if notas_asignatura
                    else 0
                )

                asignaturas_detalle.append({
                    "asignatura": asignatura,
                    "evaluaciones": evaluaciones_detalle,
                    "promedio": promedio_asignatura,
                })

            alumnos_curso_detalle.append({
                "matricula": matricula,
                "alumno": alumno,
                "promedio": round(float(promedio_alumno), 1) if promedio_alumno else 0,
                "asignaturas_detalle": asignaturas_detalle,
            })

    return render(request, "colegio/panel_admin_cursos.html", {
        "cursos": cursos,
        "curso_seleccionado": curso_seleccionado,
        "curso_seleccionado_id": curso_seleccionado.pk if curso_seleccionado else None,
        "matriculas_curso": matriculas_curso,
        "alumnos_curso_detalle": alumnos_curso_detalle,
    })


@login_required
def panel_admin_asignaturas(request):
    """Lista todas las asignaturas del sistema."""
    if not es_admin(request.user):
        return redireccionar_por_rol(request.user)

    asignatura_filtro = request.GET.get("asignatura", "").strip()
    ciclo_filtro = Curso.normalizar_ciclo(request.GET.get("ciclo", ""))
    ciclos_validos = {Curso.CICLO_KINDER, Curso.CICLO_BASICA, Curso.CICLO_MEDIA}

    nombres_asignaturas = list(
        Asignatura.objects.order_by("nombre_asignatura")
        .values_list("nombre_asignatura", flat=True)
        .distinct()
    )

    asignaturas = Asignatura.objects.select_related("curso").prefetch_related("docentes")

    if asignatura_filtro:
        asignaturas = asignaturas.filter(nombre_asignatura__iexact=asignatura_filtro)

    if ciclo_filtro in ciclos_validos:
        asignaturas = asignaturas.filter(curso__ciclo=ciclo_filtro)
    else:
        ciclo_filtro = ""

    return render(request, "colegio/panel_admin_asignaturas.html", {
        "asignaturas": asignaturas.order_by("nombre_asignatura", "curso__ciclo", "curso__nivel", "curso__seccion"),
        "nombres_asignaturas": nombres_asignaturas,
        "asignatura_filtro": asignatura_filtro,
        "ciclo_filtro": ciclo_filtro,
        "ciclos_filtro": [
            {"valor": "", "label": "Todos"},
            {"valor": Curso.CICLO_KINDER, "label": "Kinder"},
            {"valor": Curso.CICLO_BASICA, "label": "Basica"},
            {"valor": Curso.CICLO_MEDIA, "label": "Media"},
        ],
    })


@login_required
def panel_admin_matriculas(request):
    """Lista todas las matrículas y alumnos pendientes de matrícula."""
    if not es_admin(request.user):
        return redireccionar_por_rol(request.user)

    matriculas = Matricula.objects.select_related(
        "alumno",
        "alumno__usuario",
        "curso",
        "periodo"
    ).order_by("-fecha_matricula")

    alumnos_matriculados = matriculas.values_list("alumno_id", flat=True)

    alumnos_sin_matricula = list(
        Alumno.objects.select_related("usuario")
        .exclude(id__in=alumnos_matriculados)
        .exclude(estado_alumno="Matriculación cancelada")
        .order_by("apellido_alumno", "nombre_alumno")
    )

    for alumno in alumnos_sin_matricula:
        username_normalizado = alumno.usuario.username
        rut_alumno = alumno.usuario.rut

        postulacion = SolicitudPostulacion.objects.filter(
            Q(alumno_creado=alumno) |
            Q(rut_alumno_normalizado__iexact=username_normalizado) |
            Q(rut_alumno__iexact=rut_alumno),
            estado="APROBADA"
        ).order_by("-fecha_solicitud").first()

        alumno.postulacion_referencia = postulacion

    return render(request, "colegio/panel_admin_matriculas.html", {
        "matriculas": matriculas,
        "alumnos_sin_matricula": alumnos_sin_matricula,
    })

@login_required
def panel_admin_postulaciones(request):
    """
    Lista postulaciones públicas recibidas.
    Permite filtrar por estado.
    """

    if not es_admin(request.user):
        return redireccionar_por_rol(request.user)

    estado = request.GET.get("estado", "PENDIENTE")

    postulaciones = SolicitudPostulacion.objects.select_related(
        "procesada_por",
        "alumno_creado",
        "apoderado_creado",
    ).order_by("-fecha_solicitud")

    if estado in ["PENDIENTE", "APROBADA", "RECHAZADA"]:
        postulaciones = postulaciones.filter(estado=estado)
    else:
        estado = "TODAS"

    return render(request, "colegio/panel_admin_postulaciones.html", {
        "postulaciones": postulaciones,
        "estado": estado,
        "total_postulaciones": postulaciones.count(),
    })

@login_required
def aprobar_postulacion(request, pk):
    """
    Aprueba una postulación pública.

    Al aprobar:
    - Crea Usuario Apoderado.
    - Actualiza perfil Apoderado creado por señal.
    - Crea Usuario Alumno.
    - Actualiza perfil Alumno creado por señal.
    - Crea relación AlumnoApoderado.
    - Marca la solicitud como APROBADA.
    """

    if not es_admin(request.user):
        return redireccionar_por_rol(request.user)

    solicitud = get_object_or_404(
        SolicitudPostulacion,
        pk=pk,
        estado="PENDIENTE"
    )

    if request.method != "POST":
        return redirect("panel_admin_postulaciones")

    try:
        with transaction.atomic():
            # Validación final por si el RUT fue registrado después de la postulación.
            if Usuario.objects.filter(
                Q(username__iexact=solicitud.rut_alumno_normalizado) |
                Q(rut__iexact=solicitud.rut_alumno)
            ).exists():
                messages.error(
                    request,
                    "No se puede aprobar: el RUT del alumno ya existe como usuario."
                )
                return redirect("panel_admin_postulaciones")

            if Usuario.objects.filter(
                Q(username__iexact=solicitud.rut_apoderado_normalizado) |
                Q(rut__iexact=solicitud.rut_apoderado)
            ).exists():
                messages.error(
                    request,
                    "No se puede aprobar: el RUT del apoderado ya existe como usuario."
                )
                return redirect("panel_admin_postulaciones")

            if Usuario.objects.filter(email__iexact=solicitud.email_apoderado).exists():
                messages.error(
                    request,
                    "No se puede aprobar: el correo del apoderado ya existe como usuario."
                )
                return redirect("panel_admin_postulaciones")

            if Apoderado.objects.filter(email__iexact=solicitud.email_apoderado).exists():
                messages.error(
                    request,
                    "No se puede aprobar: el correo del apoderado ya existe en apoderados."
                )
                return redirect("panel_admin_postulaciones")

            data = data_desde_solicitud_postulacion(solicitud)
            resultado = crear_alumno_apoderado_desde_data(data)

            solicitud.estado = "APROBADA"
            solicitud.fecha_resolucion = timezone.now()
            solicitud.procesada_por = request.user
            solicitud.alumno_creado = resultado["alumno"]
            solicitud.apoderado_creado = resultado["apoderado"]
            solicitud.save()

        messages.success(
            request,
            "Postulación aprobada. Alumno y apoderado fueron creados correctamente."
        )

    except IntegrityError:
        messages.error(
            request,
            "No se pudo aprobar la postulación porque existe información duplicada."
        )

    except Exception as e:
        messages.error(
            request,
            f"No se pudo aprobar la postulación. Detalle: {e}"
        )

    return redirect("panel_admin_postulaciones")


@login_required
def rechazar_postulacion(request, pk):
    """
    Rechaza una postulación pública.
    No elimina la solicitud; solo cambia su estado.
    """

    if not es_admin(request.user):
        return redireccionar_por_rol(request.user)

    solicitud = get_object_or_404(
        SolicitudPostulacion,
        pk=pk,
        estado="PENDIENTE"
    )

    if request.method == "POST":
        solicitud.estado = "RECHAZADA"
        solicitud.fecha_resolucion = timezone.now()
        solicitud.procesada_por = request.user
        solicitud.observacion_admin = request.POST.get(
            "observacion_admin",
            ""
        ).strip()
        solicitud.save()

        messages.success(request, "Postulación rechazada correctamente.")

    return redirect("panel_admin_postulaciones")

@login_required
def panel_admin_reportes(request):
    """Panel de reportes para administradores."""
    if not es_admin(request.user):
        return redireccionar_por_rol(request.user)

    promedio_general = Nota.objects.aggregate(promedio=Avg("valor_nota"))["promedio"]
    promedio_general = round(float(promedio_general), 1) if promedio_general is not None else None

    total_asistencias = Asistencia.objects.count()
    total_presentes = Asistencia.objects.filter(estado_asistencia__iexact="Presente").count()
    asistencia_media = round((total_presentes / total_asistencias) * 100, 1) if total_asistencias else None

    cursos_resumen = []
    cursos = Curso.objects.all().order_by("ciclo", "nivel", "seccion")
    
    # Filtro por ciclo
    ciclo_filtro = request.GET.get("ciclo", "").strip()
    if ciclo_filtro:
        cursos = cursos.filter(ciclo=ciclo_filtro)
    
    curso_id = request.GET.get("curso_id")
    curso_seleccionado = None
    alumnos_curso = []

    for curso in cursos:
        promedio_curso = Nota.objects.filter(
            evaluacion__carga__curso=curso
        ).aggregate(promedio=Avg("valor_nota"))["promedio"]
        promedio_curso = round(float(promedio_curso), 1) if promedio_curso is not None else None

        asistencias_curso = Asistencia.objects.filter(carga__curso=curso)
        total_asistencias_curso = asistencias_curso.count()
        presentes_curso = asistencias_curso.filter(estado_asistencia__iexact="Presente").count()
        asistencia_curso = round((presentes_curso / total_asistencias_curso) * 100, 1) if total_asistencias_curso else None

        promedio_para_estado = promedio_curso if promedio_curso is not None else 0
        asistencia_para_estado = asistencia_curso if asistencia_curso is not None else 0

        if promedio_curso is None and asistencia_curso is None:
            estado = "Sin datos"
            estado_clase = "sin-datos"
        elif promedio_para_estado >= 6.0 and asistencia_para_estado >= 90:
            estado = "Excelente"
            estado_clase = "activo"
        elif promedio_para_estado < 5.0 or asistencia_para_estado < 85:
            estado = "Atención"
            estado_clase = "atencion"
        else:
            estado = "Normal"
            estado_clase = "normal"

        cursos_resumen.append({
            "curso": curso,
            "promedio": promedio_curso,
            "asistencia": asistencia_curso,
            "estado": estado,
            "estado_clase": estado_clase,
        })

    if curso_id:
        curso_seleccionado = get_object_or_404(Curso, pk=curso_id)
        matriculas = Matricula.objects.filter(
            curso=curso_seleccionado
        ).select_related(
            "alumno",
            "alumno__usuario",
            "periodo",
        ).order_by("alumno__apellido_alumno", "alumno__nombre_alumno")

        for matricula in matriculas:
            asistencias_alumno = Asistencia.objects.filter(
                alumno=matricula.alumno,
                carga__curso=curso_seleccionado,
            )
            total_asistencias_alumno = asistencias_alumno.count()
            presentes_alumno = asistencias_alumno.filter(
                estado_asistencia__iexact="Presente"
            ).count()
            asistencia_alumno = (
                round((presentes_alumno / total_asistencias_alumno) * 100, 1)
                if total_asistencias_alumno
                else None
            )

            alumnos_curso.append({
                "alumno": matricula.alumno,
                "periodo": matricula.periodo,
                "asistencia": asistencia_alumno,
            })

    return render(request, "colegio/panel_admin_reportes.html", {
        "promedio_general": promedio_general,
        "asistencia_media": asistencia_media,
        "cursos_resumen": cursos_resumen,
        "curso_seleccionado": curso_seleccionado,
        "alumnos_curso": alumnos_curso,
        "ciclo_filtro": ciclo_filtro,
    })


@login_required
def panel_admin_perfil(request):
    """Perfil del administrador."""
    if not es_admin(request.user):
        return redireccionar_por_rol(request.user)

    return render(request, "colegio/panel_admin_perfil.html")


@login_required
def panel_admin_docentes(request):
    """Lista todos los docentes registrados."""
    if not es_admin(request.user):
        return redirect("login")

    docentes = Docente.objects.select_related("usuario").prefetch_related(
        "asignaturas__curso",
        "cursos_jefatura",
    ).order_by("apellido_docente", "nombre_docente")

    docentes_info = []
    for docente in docentes:
        asignaturas = list(docente.asignaturas.all())
        docentes_info.append({
            "docente": docente,
            "asignaturas_count": len(asignaturas),
            "cursos_jefatura": list(docente.cursos_jefatura.all()),
        })

    docente_id = request.GET.get("docente_id")
    docente_seleccionado = None
    cursos_docente = []

    if docente_id:
        docente_seleccionado = get_object_or_404(Docente, pk=docente_id)
        asignaturas_docente = Asignatura.objects.filter(
            docentes=docente_seleccionado
        ).select_related("curso").order_by(
            "curso__ciclo",
            "curso__nivel",
            "curso__seccion",
            "nombre_asignatura",
        )

        cursos_por_id = {}
        for asignatura in asignaturas_docente:
            curso = asignatura.curso
            if curso.id not in cursos_por_id:
                cursos_por_id[curso.id] = {
                    "curso": curso,
                    "asignaturas": [],
                }
            cursos_por_id[curso.id]["asignaturas"].append(asignatura.nombre_asignatura)

        cursos_docente = list(cursos_por_id.values())

    return render(request, "colegio/panel_admin_docentes.html", {
        "docentes_info": docentes_info,
        "docente_seleccionado": docente_seleccionado,
        "cursos_docente": cursos_docente,
    })



@login_required
def crear_matricula_admin(request):
    """Crea una nueva matrícula desde el panel admin."""
    if not es_admin(request.user):
        return redireccionar_por_rol(request.user)

    alumno_id = request.GET.get("alumno_id")

    if request.method == "POST":
        form = MatriculaAdminForm(request.POST, alumno_id=alumno_id)

        if form.is_valid():
            try:
                matricula = form.save()

                # Reactivar alumno si venía de postulación o cancelación.
                matricula.alumno.estado_alumno = "Activo"
                matricula.alumno.save(update_fields=["estado_alumno"])

                # Asociar automáticamente apoderados existentes.
                apoderados = Apoderado.objects.filter(
                    alumnoapoderado__alumno=matricula.alumno
                )

                if apoderados.exists():
                    matricula.apoderados.set(apoderados)

                messages.success(request, "Matrícula creada correctamente.")
                return redirect("panel_admin_matriculas")

            except IntegrityError:
                form.add_error(
                    None,
                    "Ya existe una matrícula para este alumno en este período."
                )
    else:
        form = MatriculaAdminForm(alumno_id=alumno_id)

    return render(request, "colegio/form_matricula.html", {
        "form": form,
        "titulo": "Nueva Matrícula",
        "accion": "Crear",
        "postulacion_referencia": form.postulacion_referencia,
    })


@login_required
def editar_matricula_admin(request, pk):
    """Edita una matrícula existente."""
    if not es_admin(request.user):
        return redireccionar_por_rol(request.user)

    matricula = get_object_or_404(
        Matricula.objects.select_related(
            "alumno",
            "alumno__usuario",
            "curso",
            "periodo"
        ),
        pk=pk
    )

    relaciones_apoderados = AlumnoApoderado.objects.filter(
        alumno=matricula.alumno
    ).select_related(
        "apoderado",
        "apoderado__usuario"
    )

    if request.method == "POST":
        form = MatriculaAdminFormEdit(request.POST, instance=matricula)

        if form.is_valid():
            try:
                matricula = form.save()

                matricula.alumno.estado_alumno = "Activo"
                matricula.alumno.save(update_fields=["estado_alumno"])

                messages.success(request, "Matrícula actualizada correctamente.")
                return redirect("panel_admin_matriculas")

            except IntegrityError:
                form.add_error(
                    None,
                    "Ya existe una matrícula para este alumno en el período seleccionado."
                )
    else:
        form = MatriculaAdminFormEdit(instance=matricula)

    return render(request, "colegio/form_matricula.html", {
        "form": form,
        "titulo": "Editar Matrícula",
        "accion": "Guardar cambios",
        "matricula": matricula,
        "relaciones_apoderados": relaciones_apoderados,
    })

@login_required
def eliminar_matricula_admin(request, pk):
    """Elimina una matrícula con confirmación."""
    if not es_admin(request.user):
        return redireccionar_por_rol(request.user)

    matricula = get_object_or_404(Matricula, pk=pk)

    if request.method == 'POST':
        alumno = str(matricula.alumno)
        matricula.delete()
        messages.success(request, f'Matrícula de {alumno} eliminada correctamente.')
        return redirect('panel_admin_matriculas')

    return render(request, 'colegio/confirmar_eliminar_matricula.html', {
        'matricula': matricula,
    })
@login_required
def cancelar_matriculacion_admin(request, alumno_id):
    """
    Cancela el proceso de matriculación sin borrar usuario,
    alumno, apoderado ni relación AlumnoApoderado.
    """
    if not es_admin(request.user):
        return redireccionar_por_rol(request.user)

    alumno = get_object_or_404(
        Alumno.objects.select_related("usuario"),
        pk=alumno_id
    )

    if request.method != "POST":
        return redirect("panel_admin_matriculas")

    if Matricula.objects.filter(alumno=alumno).exists():
        messages.error(
            request,
            "No se puede cancelar porque el alumno ya tiene una matrícula registrada."
        )
        return redirect("panel_admin_matriculas")

    alumno.estado_alumno = "Matriculación cancelada"
    alumno.save(update_fields=["estado_alumno"])

    messages.success(
        request,
        f"Se canceló la matriculación de {alumno}. El usuario, alumno y apoderado siguen registrados."
    )

    return redirect("panel_admin_matriculas")

# ============================================================
# ACCIONES DE USUARIOS (ADMIN)
# ============================================================

@login_required
def bloquear_usuario(request, usuario_id):
    """Bloquea o desbloquea un usuario cambiando su estado is_active."""
    if not es_admin(request.user):
        return redireccionar_por_rol(request.user)

    usuario = get_object_or_404(Usuario, id=usuario_id)

    if usuario == request.user:
        messages.error(request, "No puedes bloquear tu propia cuenta.")
    else:
        usuario.is_active = not usuario.is_active
        usuario.save()
        estado = "desbloqueado" if usuario.is_active else "bloqueado"
        messages.success(request, f"El usuario {usuario.username} ha sido {estado}.")

    return redirect("panel_admin_usuarios")


@login_required
def eliminar_usuario(request, usuario_id):
    """Elimina permanentemente un usuario y su perfil asociado (CASCADE)."""
    if not es_admin(request.user):
        return redireccionar_por_rol(request.user)

    usuario = get_object_or_404(Usuario, id=usuario_id)

    if usuario == request.user:
        messages.error(request, "No puedes eliminar tu propia cuenta.")
    else:
        username = usuario.username
        usuario.delete()
        messages.success(request, f"El usuario {username} ha sido eliminado permanentemente.")

    return redirect("panel_admin_usuarios")


# ============================================================
# CRUD DE CURSOS (ADMIN)
# ============================================================

@login_required
def crear_curso(request):
    """Crea un nuevo curso."""
    if request.method == "POST":
        form = CursoForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Curso creado exitosamente.")
            return redirect("panel_admin_cursos")
        messages.error(request, "Error al crear el curso. Revisa el formulario.")
    else:
        form = CursoForm()

    return render(request, "colegio/form_curso.html", {"form": form, "titulo": "Crear Nuevo Curso"})


@login_required
def editar_curso(request, pk):
    """Edita un curso existente."""
    curso = get_object_or_404(Curso, pk=pk)

    if request.method == "POST":
        form = CursoForm(request.POST, instance=curso)
        if form.is_valid():
            form.save()
            messages.success(request, "Curso actualizado correctamente.")
            return redirect("panel_admin_cursos")
        messages.error(request, "Error al actualizar el curso.")
    else:
        form = CursoForm(instance=curso)

    return render(request, "colegio/form_curso.html", {
        "form": form,
        "titulo": "Editar Curso",
        "curso": curso,
    })


@login_required
def eliminar_curso(request, pk):
    """Elimina físicamente un curso (en cascada)."""
    curso = get_object_or_404(Curso, pk=pk)
    nombre = f"{curso.nivel}° {curso.seccion}"

    try:
        curso.delete()
        messages.success(request, f"El curso '{nombre}' fue eliminado permanentemente.")
    except Exception:
        messages.error(request, "No se pudo eliminar el curso: está asociado a matrículas o cargas.")

    return redirect("panel_admin_cursos")


def carga_masiva_cursos(request):
    """Crea cursos en masa desde un archivo Excel (.xlsx / .xls)."""
    if request.method == "POST":
        archivo = request.FILES.get("archivo_excel")

        if not archivo:
            messages.error(request, "Por favor, selecciona un archivo.")
            return redirect("carga_masiva_cursos")

        if not archivo.name.endswith((".xlsx", ".xls")):
            messages.error(request, "Formato no válido. Solo se aceptan archivos Excel.")
            return redirect("carga_masiva_cursos")

        try:
            df = pd.read_excel(archivo)
            creados = 0
            omitidos = 0

            for _, row in df.iterrows():
                ciclo = Curso.normalizar_ciclo(row.get("Ciclo", ""))
                nivel = row.get("Nivel")
                seccion = str(row.get("Seccion", "")).strip().upper()

                if ciclo == Curso.CICLO_KINDER and not pd.notna(nivel):
                    nivel = 1

                if ciclo and pd.notna(nivel) and seccion:
                    try:
                        nivel = int(nivel)
                        error_nivel = Curso.validar_nivel_por_ciclo(ciclo, nivel)
                        if error_nivel:
                            omitidos += 1
                            continue

                        if not Curso.objects.filter(ciclo=ciclo, nivel=nivel, seccion=seccion).exists():
                            Curso.objects.create(ciclo=ciclo, nivel=nivel, seccion=seccion, estado_curso=True)
                            creados += 1
                        else:
                            omitidos += 1
                    except ValueError:
                        omitidos += 1
                else:
                    omitidos += 1

            messages.success(request, f"Carga completada: {creados} creados, {omitidos} omitidos.")
            return redirect("panel_admin_cursos")

        except Exception as e:
            messages.error(request, f"Error al procesar el archivo. Detalle: {e}")
            return redirect("carga_masiva_cursos")

    return render(request, "colegio/carga_masiva_cursos.html")


# ============================================================
# CRUD DE ASIGNATURAS (ADMIN)
# ============================================================

@login_required
def crear_asignatura(request):
    """Crea una nueva asignatura."""
    if not es_admin(request.user):
        return redirect("login")

    if request.method == "POST":
        form = AsignaturaForm(request.POST)
        if form.is_valid():
            asignatura = form.save()
            sincronizar_cargas_asignatura(asignatura)
            messages.success(request, "Asignatura creada exitosamente.")
            return redirect("panel_admin_asignaturas")
    else:
        form = AsignaturaForm()

    return render(request, "colegio/form_curso.html", {"form": form, "titulo": "Nueva Asignatura"})


@login_required
def editar_asignatura(request, id):
    """Edita una asignatura existente."""
    if not es_admin(request.user):
        return redirect("login")

    asignatura = get_object_or_404(Asignatura, id=id)

    if request.method == "POST":
        form = AsignaturaForm(request.POST, instance=asignatura)
        if form.is_valid():
            try:
                with transaction.atomic():
                    sincronizar_docentes_removidos_asignatura(
                        asignatura,
                        form.cleaned_data["docentes"],
                    )
                    asignatura = form.save()
                    sincronizar_cargas_asignatura(asignatura)

                messages.success(request, "Asignatura actualizada correctamente.")
                return redirect("panel_admin_asignaturas")
            except ValueError as e:
                form.add_error("docentes", str(e))
    else:
        form = AsignaturaForm(instance=asignatura)

    return render(request, "colegio/form_curso.html", {
        "form": form,
        "titulo": f"Editar Asignatura: {asignatura.nombre_asignatura}",
    })


@login_required
def eliminar_asignatura(request, id):
    """Elimina físicamente una asignatura."""
    if not es_admin(request.user):
        return redirect("login")

    asignatura = get_object_or_404(Asignatura, id=id)
    asignatura.delete()
    messages.success(request, "Asignatura eliminada permanentemente.")
    return redirect("panel_admin_asignaturas")


@login_required
def carga_masiva_asignaturas(request):
    """Crea asignaturas en masa desde un archivo Excel."""
    if not es_admin(request.user):
        return redirect("login")

    if request.method == "POST" and request.FILES.get("archivo_excel"):
        try:
            df = pd.read_excel(request.FILES["archivo_excel"])
            creadas = 0

            for _, row in df.iterrows():
                nombre = str(row.get("Nombre", "")).strip()
                descripcion = str(row.get("Descripcion", "")).strip()

                if nombre and nombre != "nan":
                    _, created = Asignatura.objects.get_or_create(
                        nombre_asignatura=nombre,
                        defaults={"descripcion": descripcion if descripcion != "nan" else ""},
                    )
                    if created:
                        creadas += 1

            messages.success(request, f"Carga completada: {creadas} asignaturas creadas.")
            return redirect("panel_admin_asignaturas")

        except Exception as e:
            messages.error(request, f"Error al procesar el archivo. Detalle: {e}")
            return redirect("panel_admin_asignaturas")

    return render(request, "colegio/carga_masiva_base.html", {"titulo": "Carga Masiva de Asignaturas"})


# ============================================================
# CRUD DE DOCENTES (ADMIN)
# ============================================================

@login_required
def crear_docente(request):
    """Crea un docente y su usuario de acceso vinculado."""
    if request.method == "POST":
        form = DocenteForm(request.POST)
        if form.is_valid():
            rut = form.cleaned_data["rut"]
            email = form.cleaned_data["email_institucional"]

            if Usuario.objects.filter(rut=rut).exists():
                form.add_error("rut", "Este RUT ya está registrado.")
                return render(request, "colegio/crear_docente.html", {"form": form})

            if Usuario.objects.filter(email=email).exists() or Docente.objects.filter(email_institucional=email).exists():
                form.add_error("email_institucional", "Este correo ya está en uso.")
                return render(request, "colegio/crear_docente.html", {"form": form})

            try:
                with transaction.atomic():
                    username = rut.replace(".", "").replace("-", "")
                    usuario = Usuario.objects.create_user(
                        username=username,
                        email=email,
                        password=username[:6],
                        first_name=form.cleaned_data["nombre_docente"],
                        last_name=form.cleaned_data["apellido_docente"],
                        tipo_usuario="DOCENTE",
                        rut=rut,
                    )
                    docente = Docente.objects.get(usuario=usuario)
                    docente.nombre_docente = form.cleaned_data["nombre_docente"]
                    docente.apellido_docente = form.cleaned_data["apellido_docente"]
                    docente.telefono = form.cleaned_data["telefono"]
                    docente.email_institucional = email
                    docente.save()

                return redirect("panel_admin_docentes")

            except Exception as e:
                messages.error(request, f"Error al guardar: {e}")
    else:
        form = DocenteForm()

    return render(request, "colegio/crear_docente.html", {"form": form})


@login_required
def editar_docente(request, pk):
    """Edita los datos de un docente y sincroniza su usuario."""
    docente = get_object_or_404(Docente, pk=pk)

    if request.method == "POST":
        form = DocenteForm(request.POST, instance=docente)
        if form.is_valid():
            rut = form.cleaned_data["rut"]

            if Usuario.objects.filter(rut=rut).exclude(pk=docente.usuario.pk).exists():
                form.add_error("rut", "Este RUT pertenece a otro usuario.")
                return render(request, "colegio/crear_docente.html", {"form": form, "docente": docente})

            try:
                with transaction.atomic():
                    docente = form.save(commit=False)
                    docente.save()

                    usuario = docente.usuario
                    usuario.rut = rut
                    usuario.first_name = docente.nombre_docente
                    usuario.last_name = docente.apellido_docente
                    usuario.email = docente.email_institucional
                    usuario.save()

                messages.success(request, "Docente actualizado correctamente.")
                return redirect("panel_admin_docentes")

            except Exception as e:
                messages.error(request, f"Error al actualizar: {e}")
    else:
        form = DocenteForm(instance=docente, initial={"rut": docente.usuario.rut})

    return render(request, "colegio/crear_docente.html", {"form": form, "docente": docente})


@login_required
def eliminar_docente(request, pk):
    """Elimina un docente y su usuario asociado (CASCADE)."""
    if not es_admin(request.user):
        return redirect("login")

    docente = get_object_or_404(Docente, pk=pk)
    nombre = f"{docente.nombre_docente} {docente.apellido_docente}"
    docente.usuario.delete()
    messages.success(request, f"Docente {nombre} eliminado correctamente.")
    return redirect("panel_admin_docentes")


# ============================================================
# CREAR PERSONAS (ADMIN) — Alumno / Apoderado
# ============================================================

@login_required
def crear_alumno_view(request):
    """
    Crea un alumno y su usuario de acceso vinculado.

    Se crea primero Usuario.
    La señal post_save crea Alumno.
    Luego se recupera y actualiza el perfil Alumno.
    """

    if request.user.tipo_usuario != "ADMIN":
        return redireccionar_por_rol(request.user)

    if request.method == "POST":
        form = AlumnoAdminForm(request.POST)

        if form.is_valid():
            try:
                with transaction.atomic():
                    usuario, username, password_temporal = crear_usuario_con_rol(
                        rut=form.cleaned_data["rut"],
                        tipo_usuario="ALUMNO",
                        first_name=form.cleaned_data["nombre_alumno"],
                        last_name=form.cleaned_data["apellido_alumno"],
                    )

                    alumno = Alumno.objects.select_for_update().get(
                        usuario=usuario
                    )
                    alumno.nombre_alumno = form.cleaned_data["nombre_alumno"]
                    alumno.apellido_alumno = form.cleaned_data["apellido_alumno"]
                    alumno.fecha_nacimiento = form.cleaned_data["fecha_nacimiento"]
                    alumno.genero = form.cleaned_data["genero"]
                    alumno.estado_alumno = form.cleaned_data["estado_alumno"]
                    alumno.save()

                return render(request, "colegio/alumno_form.html", {
                    "form": AlumnoAdminForm(),
                    "mensaje": f"Alumno creado. Usuario: {username} | Contraseña: {password_temporal}",
                })

            except IntegrityError:
                form.add_error("rut", "Este RUT ya está registrado.")

            except Exception as e:
                form.add_error(None, f"No se pudo crear el alumno. Detalle: {e}")

    else:
        form = AlumnoAdminForm()

    return render(request, "colegio/alumno_form.html", {
        "form": form
    })


@login_required
def crear_apoderado_view(request):
    """
    Crea un apoderado y su usuario de acceso vinculado.

    Se crea primero Usuario.
    La señal post_save crea Apoderado.
    Luego se recupera y actualiza el perfil Apoderado.
    """

    if request.user.tipo_usuario != "ADMIN":
        return redireccionar_por_rol(request.user)

    if request.method == "POST":
        form = ApoderadoAdminForm(request.POST)

        if form.is_valid():
            try:
                with transaction.atomic():
                    usuario, username, password_temporal = crear_usuario_con_rol(
                        rut=form.cleaned_data["rut"],
                        tipo_usuario="APODERADO",
                        first_name=form.cleaned_data["nombre_apoderado"],
                        last_name=form.cleaned_data["apellido_apoderado"],
                        email=form.cleaned_data["email"],
                    )

                    apoderado = Apoderado.objects.select_for_update().get(
                        usuario=usuario
                    )
                    apoderado.nombre_apoderado = form.cleaned_data["nombre_apoderado"]
                    apoderado.apellido_apoderado = form.cleaned_data["apellido_apoderado"]
                    apoderado.direccion = form.cleaned_data["direccion"]
                    apoderado.telefono = form.cleaned_data["telefono"]
                    apoderado.email = form.cleaned_data["email"]
                    apoderado.save()

                return render(request, "colegio/apoderado_form.html", {
                    "form": ApoderadoAdminForm(),
                    "mensaje": f"Apoderado creado. Usuario: {username} | Contraseña: {password_temporal}",
                })

            except IntegrityError:
                form.add_error("rut", "Este RUT ya está registrado.")

            except Exception as e:
                form.add_error(None, f"No se pudo crear el apoderado. Detalle: {e}")

    else:
        form = ApoderadoAdminForm()

    return render(request, "colegio/apoderado_form.html", {
        "form": form
    })


# ============================================================
# MATRÍCULA
# ============================================================

def crear_matricula_view(request):
    """
    Crea una matrícula y asocia automáticamente Alumno con Apoderado
    en la tabla AlumnoApoderado.
    """
    if request.method == "POST":
        form = MatriculaForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    matricula = form.save()
                    AlumnoApoderado.objects.get_or_create(
                        alumno=matricula.alumno,
                        apoderado=matricula.apoderado,
                        defaults={
                            "parentesco": matricula.parentesco,
                            "is_principal": matricula.is_apoderado_principal,
                        },
                    )

                return render(request, "colegio/matricula_form.html", {
                    "form": MatriculaForm(),
                    "mensaje": "Matrícula creada y apoderado asociado correctamente.",
                })

            except IntegrityError:
                form.add_error(None, "Ya existe una matrícula para este alumno en este período.")
    else:
        form = MatriculaForm()

    return render(request, "colegio/matricula_form.html", {"form": form})


def lista_matriculas(request):
    """Lista todas las matrículas registradas."""
    matriculas = Matricula.objects.select_related("alumno", "curso", "periodo").all()
    return render(request, "colegio/lista_matriculas.html", {"matriculas": matriculas})


# ============================================================
# PANEL DOCENTE
# ============================================================

@login_required
def panel_docente(request):
    """
    Panel principal del docente.
    Muestra métricas: cursos asignados, total alumnos y evaluaciones creadas.
    """
    if request.user.tipo_usuario != "DOCENTE":
        return redireccionar_por_rol(request.user)

    try:
        docente = Docente.objects.get(usuario=request.user)
        asegurar_cargas_docente(docente)

        cargas = CargaAcademica.objects.filter(
            docente=docente
        ).select_related("curso", "asignatura", "periodo")

        total_cursos = cargas.count()

        cursos_ids = cargas.values_list("curso_id", flat=True)
        total_alumnos = Matricula.objects.filter(
            curso_id__in=cursos_ids
        ).values("alumno").distinct().count()

        total_evaluaciones = Evaluacion.objects.filter(carga__docente=docente).count()

    except Docente.DoesNotExist:
        docente = None
        cargas = []
        total_cursos = 0
        total_alumnos = 0
        total_evaluaciones = 0

    return render(request, "colegio/panel_docente.html", {
        "docente": docente,
        "cargas": cargas,
        "total_cursos": total_cursos,
        "total_alumnos": total_alumnos,
        "total_evaluaciones": total_evaluaciones,
    })


@login_required
def panel_docente_cursos(request):
    """
    Lista los cursos y asignaturas asignados al docente,
    con el total de alumnos matriculados por curso.
    """
    if request.user.tipo_usuario != "DOCENTE":
        return redireccionar_por_rol(request.user)

    try:
        docente = Docente.objects.get(usuario=request.user)
        asegurar_cargas_docente(docente)

        cargas = CargaAcademica.objects.filter(
            docente=docente
        ).select_related("curso", "asignatura", "periodo")

        cursos = [
            {
                "carga": carga,
                "curso": carga.curso,
                "asignatura": carga.asignatura,
                "periodo": carga.periodo,
                "total_alumnos": Matricula.objects.filter(
                    curso=carga.curso,
                    periodo=carga.periodo,
                ).count(),
            }
            for carga in cargas
        ]

    except Docente.DoesNotExist:
        cursos = []

    return render(request, "colegio/panel_docente_cursos.html", {"cursos": cursos})


@login_required
def panel_docente_notas(request):
    docente = get_object_or_404(Docente, usuario=request.user)
    asegurar_cargas_docente(docente)

    cargas = CargaAcademica.objects.filter(
        docente=docente
    ).select_related("curso", "asignatura", "periodo")

    carga_id = request.GET.get("carga_id")
    carga_seleccionada = None

    if carga_id:
        carga_seleccionada = get_object_or_404(CargaAcademica, id=carga_id, docente=docente)
        evaluaciones = Evaluacion.objects.filter(
            carga=carga_seleccionada
        ).select_related(
            "carga__curso",
            "carga__asignatura",
        ).order_by(
            "numero_evaluacion",
            "fecha",
        )
    else:
        evaluaciones = Evaluacion.objects.none()

    notas_registradas = Nota.objects.none()
    notas_por_evaluacion = []
    if carga_seleccionada:
        notas_registradas = Nota.objects.filter(
            evaluacion__carga=carga_seleccionada
        ).select_related(
            "alumno",
            "evaluacion",
            "evaluacion__carga__curso",
        ).order_by(
            "evaluacion__numero_evaluacion",
            "evaluacion__fecha",
            "alumno__apellido_alumno",
            "alumno__nombre_alumno",
        )
        for evaluacion in evaluaciones:
            notas_por_evaluacion.append({
                "evaluacion": evaluacion,
                "notas": list(notas_registradas.filter(evaluacion=evaluacion)),
            })

    return render(request, "colegio/panel_docente_notas.html", {
        "cargas": cargas,
        "carga_seleccionada": carga_seleccionada,
        "evaluaciones": evaluaciones,
        "notas_registradas": notas_registradas,
        "notas_por_evaluacion": notas_por_evaluacion,
    })


@login_required
def crear_evaluacion(request):
    docente = get_object_or_404(Docente, usuario=request.user)
    asegurar_cargas_docente(docente)

    cargas = CargaAcademica.objects.filter(
        docente=docente
    ).select_related("curso", "asignatura", "periodo")

    carga_id_preseleccionada = request.GET.get("carga_id")

    if request.method == "POST":
        carga_id  = request.POST.get("carga")
        nombre    = request.POST.get("nombre_evaluacion", "").strip()
        tipo      = request.POST.get("tipo_evaluacion", "").strip()
        fecha     = request.POST.get("fecha")
        numero    = request.POST.get("numero_evaluacion")

        if not all([carga_id, nombre, tipo, fecha, numero]):
            messages.error(request, "Todos los campos son obligatorios.")
            return render(request, "colegio/crear_evaluacion.html", {
                "cargas": cargas,
                "carga_id_preseleccionada": carga_id_preseleccionada,
            })

        carga = get_object_or_404(CargaAcademica, id=carga_id, docente=docente)

        evaluacion = Evaluacion.objects.create(
            carga=carga,
            nombre_evaluacion=nombre,
            tipo_evaluacion=tipo,
            porcentaje=0,
            fecha=fecha,
            numero_evaluacion=numero,
        )

        messages.success(request, f'Evaluación "{nombre}" creada correctamente.')
        return redirect(f"{reverse('panel_docente_notas')}?carga_id={carga.id}")

    return render(request, "colegio/crear_evaluacion.html", {
        "cargas": cargas,
        "carga_id_preseleccionada": carga_id_preseleccionada,
    })


@login_required
def ingresar_notas(request, evaluacion_id):
    """
    Paso 2 del flujo de notas: muestra todos los alumnos matriculados
    en el curso de la evaluación y permite ingresar o editar sus notas.
    Usa update_or_create para respetar el constraint uq_nota_evaluacion_alumno.
    """
    docente    = get_object_or_404(Docente, usuario=request.user)
    evaluacion = get_object_or_404(Evaluacion, id=evaluacion_id, carga__docente=docente)

    matriculas = Matricula.objects.filter(
        curso=evaluacion.carga.curso,
        periodo=evaluacion.carga.periodo,
    ).select_related("alumno")

    notas_existentes  = Nota.objects.filter(evaluacion=evaluacion)
    alumnos_con_nota  = {n.alumno_id: n for n in notas_existentes}

    if request.method == "POST":
        errores   = []
        guardadas = 0

        for matricula in matriculas:
            alumno = matricula.alumno
            valor  = request.POST.get(f"nota_{alumno.id}", "").strip()
            obs    = request.POST.get(f"obs_{alumno.id}", "").strip()

            if not valor:
                continue

            try:
                valor_decimal = float(valor)
                if not (1.0 <= valor_decimal <= 7.0):
                    raise ValueError
            except ValueError:
                errores.append(f"{alumno}: valor inválido '{valor}' (debe ser 1.0 – 7.0)")
                continue

            Nota.objects.update_or_create(
                evaluacion=evaluacion,
                alumno=alumno,
                defaults={"valor_nota": valor_decimal, "observacion": obs or None},
            )
            guardadas += 1

        for e in errores:
            messages.warning(request, e)

        if guardadas:
            messages.success(request, f"{guardadas} nota(s) guardada(s) correctamente.")

        return redirect("ingresar_notas", evaluacion_id=evaluacion.id)

    alumnos_data = [
        {"alumno": m.alumno, "nota": alumnos_con_nota.get(m.alumno.id)}
        for m in matriculas
    ]

    return render(request, "colegio/ingresar_notas.html", {
        "evaluacion": evaluacion,
        "alumnos_data": alumnos_data,
    })

@login_required
def editar_evaluacion(request, evaluacion_id):
    docente = get_object_or_404(Docente, usuario=request.user)
    asegurar_cargas_docente(docente)
    evaluacion = get_object_or_404(Evaluacion, id=evaluacion_id, carga__docente=docente)

    cargas = CargaAcademica.objects.filter(
        docente=docente
    ).select_related("curso", "asignatura", "periodo")

    if request.method == "POST":
        carga_id   = request.POST.get("carga")
        nombre     = request.POST.get("nombre_evaluacion", "").strip()
        tipo       = request.POST.get("tipo_evaluacion", "").strip()
        fecha      = request.POST.get("fecha")
        numero     = request.POST.get("numero_evaluacion")

        if not all([carga_id, nombre, tipo, fecha, numero]):
            messages.error(request, "Todos los campos son obligatorios.")
        else:
            carga = get_object_or_404(CargaAcademica, id=carga_id, docente=docente)
            evaluacion.carga = carga
            evaluacion.nombre_evaluacion = nombre
            evaluacion.tipo_evaluacion = tipo
            evaluacion.fecha = fecha
            evaluacion.numero_evaluacion = numero
            evaluacion.save()

            messages.success(request, "Evaluación actualizada correctamente.")
            return redirect(f"{reverse('panel_docente_notas')}?carga_id={carga.id}")

    return render(request, "colegio/editar_evaluacion.html", {
        "evaluacion": evaluacion,
        "cargas": cargas,
    })


@login_required
def eliminar_evaluacion(request, evaluacion_id):
    docente = get_object_or_404(Docente, usuario=request.user)
    evaluacion = get_object_or_404(Evaluacion, id=evaluacion_id, carga__docente=docente)

    if request.method == "POST":
        carga_id = evaluacion.carga.id
        nombre = evaluacion.nombre_evaluacion
        evaluacion.delete()
        messages.success(request, f'Evaluación "{nombre}" eliminada correctamente.')
        return redirect(f"{reverse('panel_docente_notas')}?carga_id={carga_id}")

    return redirect(f"{reverse('panel_docente_notas')}?carga_id={evaluacion.carga.id}")


@login_required
def panel_docente_asistencia(request):
    """
    Permite al docente registrar o editar la asistencia diaria.
    Flujo:
    1. El docente selecciona carga y fecha (GET con parámetros).
    2. Se listan los alumnos matriculados en ese curso.
    3. Al guardar (POST), se crea o actualiza cada registro Asistencia.
    """
    if request.user.tipo_usuario != "DOCENTE":
        return redireccionar_por_rol(request.user)

    docente = get_object_or_404(Docente, usuario=request.user)
    asegurar_cargas_docente(docente)

    cargas = CargaAcademica.objects.filter(
        docente=docente
    ).select_related("curso", "asignatura", "periodo")

    # ── Leer parámetros de filtro (GET o POST) ──────────────────
    carga_id = request.POST.get("carga_id") or request.GET.get("carga_id")
    fecha    = request.POST.get("fecha")    or request.GET.get("fecha")

    carga_seleccionada = None
    alumnos_data       = []

    if carga_id and fecha:
        carga_seleccionada = get_object_or_404(CargaAcademica, id=carga_id, docente=docente)

        matriculas = Matricula.objects.filter(
            curso=carga_seleccionada.curso,
            periodo=carga_seleccionada.periodo,
        ).select_related("alumno")

        # Asistencias ya registradas para esa carga y fecha
        registros_existentes = Asistencia.objects.filter(
            carga=carga_seleccionada,
            fecha=fecha,
        )
        asistencia_map = {a.alumno_id: a for a in registros_existentes}

        if request.method == "POST" and "guardar" in request.POST:
            guardadas = 0

            for matricula in matriculas:
                alumno = matricula.alumno
                estado = request.POST.get(f"estado_{alumno.id}", "Ausente")
                obs    = request.POST.get(f"obs_{alumno.id}", "").strip()
                if estado == "Presente":
                    obs = ""

                Asistencia.objects.update_or_create(
                    alumno=alumno,
                    carga=carga_seleccionada,
                    fecha=fecha,
                    defaults={
                        "estado_asistencia": estado,
                        "observacion": obs or None,
                    },
                )
                guardadas += 1

            messages.success(request, f"Asistencia guardada para {guardadas} alumno(s).")
            return redirect(
                f"{request.path}?carga_id={carga_id}&fecha={fecha}"
            )

        # Armar lista de alumnos con su estado actual si existe
        for matricula in matriculas:
            alumno = matricula.alumno
            registro = asistencia_map.get(alumno.id)
            alumnos_data.append({
                "alumno": alumno,
                "estado_actual": registro.estado_asistencia if registro else "Presente",
                "observacion": registro.observacion if registro else "",
            })

    return render(request, "colegio/panel_docente_asistencia.html", {
        "cargas": cargas,
        "carga_seleccionada": carga_seleccionada,
        "carga_id": carga_id,
        "fecha": fecha,
        "alumnos_data": alumnos_data,
    })


@login_required
def panel_docente_alumnos(request):
    """
    Lista los alumnos matriculados en los cursos asignados al docente,
    con su curso, correo y estado.
    """
    if request.user.tipo_usuario != "DOCENTE":
        return redireccionar_por_rol(request.user)

    try:
        docente = Docente.objects.get(usuario=request.user)
        asegurar_cargas_docente(docente)

        cargas = CargaAcademica.objects.filter(
            docente=docente
        ).select_related("curso")

        alumnos = [
            {
                "nombre": f"{m.alumno.nombre_alumno} {m.alumno.apellido_alumno}",
                "curso": carga.curso,
                "correo": m.alumno.usuario.email,
                "estado": m.alumno.estado_alumno,
            }
            for carga in cargas
            for m in Matricula.objects.filter(curso=carga.curso).select_related("alumno")
        ]

    except Docente.DoesNotExist:
        alumnos = []

    return render(request, "colegio/panel_docente_alumnos.html", {"alumnos": alumnos})


@login_required
def panel_docente_jefatura(request):
    if request.user.tipo_usuario != "DOCENTE":
        return redireccionar_por_rol(request.user)

    docente = get_object_or_404(Docente, usuario=request.user)
    cursos_jefatura = Curso.objects.filter(
        profesor_jefe=docente,
        estado_curso=True,
    ).order_by("ciclo", "nivel", "seccion")

    curso = cursos_jefatura.first()
    if not curso:
        return redirect("panel_docente")

    matriculas = Matricula.objects.filter(
        curso=curso,
        estado__iexact="Activa",
    ).select_related(
        "alumno",
        "alumno__usuario",
        "periodo",
    ).order_by(
        "alumno__apellido_alumno",
        "alumno__nombre_alumno",
    )

    alumnos_ids = list(matriculas.values_list("alumno_id", flat=True))
    asignaturas_curso = list(
        Asignatura.objects.filter(
            curso=curso,
            estado_asignatura=True,
        ).order_by("nombre_asignatura")
    )
    evaluaciones_curso = Evaluacion.objects.filter(
        carga__curso=curso,
        carga__asignatura__in=asignaturas_curso,
    ).select_related(
        "carga",
        "carga__asignatura",
    ).order_by(
        "carga__asignatura__nombre_asignatura",
        "numero_evaluacion",
        "fecha",
    )
    evaluaciones_por_asignatura = {
        asignatura.id: []
        for asignatura in asignaturas_curso
    }
    for evaluacion in evaluaciones_curso:
        evaluaciones_por_asignatura.setdefault(evaluacion.carga.asignatura_id, []).append(evaluacion)

    notas_curso = Nota.objects.filter(
        alumno_id__in=alumnos_ids,
        evaluacion__carga__curso=curso,
    ).select_related(
        "evaluacion",
        "evaluacion__carga",
        "evaluacion__carga__asignatura",
    )
    promedio_general = notas_curso.aggregate(promedio=Avg("valor_nota"))["promedio"] or 0

    asistencias_curso = Asistencia.objects.filter(
        alumno_id__in=alumnos_ids,
        carga__curso=curso,
    )
    total_asistencias = asistencias_curso.count()
    total_presentes = asistencias_curso.filter(estado_asistencia__iexact="Presente").count()
    asistencia_general = round((total_presentes / total_asistencias) * 100, 1) if total_asistencias else 0

    alumnos_resumen = []
    for matricula in matriculas:
        alumno = matricula.alumno
        notas_alumno = notas_curso.filter(alumno=alumno)
        promedio_alumno = notas_alumno.aggregate(promedio=Avg("valor_nota"))["promedio"] or 0
        notas_por_evaluacion = {
            nota.evaluacion_id: nota
            for nota in notas_alumno
        }

        asignaturas_detalle = []
        for asignatura in asignaturas_curso:
            evaluaciones_detalle = []
            notas_asignatura = []

            for evaluacion in evaluaciones_por_asignatura.get(asignatura.id, []):
                nota = notas_por_evaluacion.get(evaluacion.id)
                if nota:
                    notas_asignatura.append(nota.valor_nota)

                evaluaciones_detalle.append({
                    "evaluacion": evaluacion,
                    "nota": nota,
                })

            promedio_asignatura = (
                round(float(sum(notas_asignatura) / len(notas_asignatura)), 1)
                if notas_asignatura
                else 0
            )

            asignaturas_detalle.append({
                "asignatura": asignatura,
                "evaluaciones": evaluaciones_detalle,
                "promedio": promedio_asignatura,
            })

        asistencias_alumno = asistencias_curso.filter(alumno=alumno)
        total_alumno = asistencias_alumno.count()
        presentes_alumno = asistencias_alumno.filter(estado_asistencia__iexact="Presente").count()
        asistencia_alumno = round((presentes_alumno / total_alumno) * 100, 1) if total_alumno else 0

        alumnos_resumen.append({
            "alumno": alumno,
            "matricula": matricula,
            "promedio": round(float(promedio_alumno), 1) if promedio_alumno else 0,
            "asistencia": asistencia_alumno,
            "presentes": presentes_alumno,
            "total_asistencias": total_alumno,
            "asignaturas_detalle": asignaturas_detalle,
        })

    return render(request, "colegio/panel_docente_jefatura.html", {
        "docente": docente,
        "curso": curso,
        "cursos_jefatura": cursos_jefatura,
        "total_alumnos": len(alumnos_resumen),
        "promedio_general": round(float(promedio_general), 1) if promedio_general else 0,
        "asistencia_general": asistencia_general,
        "alumnos_resumen": alumnos_resumen,
    })


@login_required
def panel_docente_perfil(request):
    """Muestra el perfil completo del docente con sus asignaturas asignadas."""
    if request.user.tipo_usuario != "DOCENTE":
        return redireccionar_por_rol(request.user)

    try:
        docente = Docente.objects.get(usuario=request.user)
        asegurar_cargas_docente(docente)
        cargas = CargaAcademica.objects.filter(
            docente=docente
        ).select_related("curso", "asignatura", "periodo")
    except Docente.DoesNotExist:
        docente = None
        cargas = []

    return render(request, "colegio/panel_docente_perfil.html", {
        "docente": docente,
        "cargas": cargas,
    })


# ============================================================
# PANEL ALUMNO
# ============================================================

def obtener_matricula_actual_alumno(alumno):
    """
    Retorna la matricula que define el curso y periodo actual del alumno.
    Si no hay matricula activa, usa la ultima registrada para no dejar el panel vacio.
    """
    matriculas = Matricula.objects.filter(
        alumno=alumno
    ).select_related(
        "curso",
        "periodo",
    ).order_by(
        "-periodo__anio",
        "-periodo__semestre",
        "-fecha_matricula",
        "-id",
    )
    return matriculas.filter(estado__iexact="Activa").first() or matriculas.first()


def obtener_asignaturas_de_matricula(matricula):
    """
    Obtiene la malla del curso del alumno.
    No depende de CargaAcademica, porque una asignatura debe aparecer aunque aun no tenga docente.
    """
    if not matricula:
        return Asignatura.objects.none()

    return Asignatura.objects.filter(
        curso=matricula.curso,
        estado_asignatura=True,
    ).prefetch_related(
        "docentes",
    ).order_by(
        "nombre_asignatura",
    )


@login_required
def panel_alumno(request):
    alumno = Alumno.objects.get(usuario=request.user)

    # Promedio general de todas las notas del alumno
    promedio = Nota.objects.filter(alumno=alumno).aggregate(
        promedio=Avg('valor_nota')
    )['promedio']
    promedio = round(promedio, 1) if promedio else 0

    # Porcentaje de asistencia
    total_clases = Asistencia.objects.filter(alumno=alumno).count()
    presentes = Asistencia.objects.filter(
        alumno=alumno,
        estado_asistencia='Presente'  # ajusta al valor exacto que uses en tu BD
    ).count()
    asistencia_pct = round((presentes / total_clases) * 100) if total_clases > 0 else 0

    # Número de asignaturas (matrícula activa más reciente)
    # Cuenta la malla del curso matriculado, no asignaciones individuales al alumno.
    matricula = obtener_matricula_actual_alumno(alumno)
    num_asignaturas = obtener_asignaturas_de_matricula(matricula).count()

    # Últimas 5 evaluaciones con nota
    ultimas_notas = Nota.objects.filter(
        alumno=alumno
    ).select_related(
        'evaluacion',
        'evaluacion__carga',
        'evaluacion__carga__asignatura'
    ).order_by('-fecha_registro')[:5]

    context = {
        'promedio': promedio,
        'asistencia_pct': asistencia_pct,
        'periodo': matricula.periodo if matricula else None,
        'num_asignaturas': num_asignaturas,
        'ultimas_notas': ultimas_notas,
    }
    return render(request, 'colegio/panel_alumno.html', context)


@login_required
def panel_alumno_asignaturas(request):
    alumno = Alumno.objects.get(usuario=request.user)

    # Matrícula activa más reciente
    # El alumno ve la malla definida para su curso actual.
    matricula = obtener_matricula_actual_alumno(alumno)
    asignaturas = obtener_asignaturas_de_matricula(matricula)
    total = asignaturas.count()

    context = {
        'matricula': matricula,
        'periodo': matricula.periodo if matricula else None,
        'asignaturas': asignaturas,
        'total_asignaturas': total,
    }
    return render(request, 'colegio/panel_alumno_asignatura.html', context)


@login_required
def panel_alumno_notas(request):
    alumno = Alumno.objects.get(usuario=request.user)
    matricula = obtener_matricula_actual_alumno(alumno)
    asignaturas = obtener_asignaturas_de_matricula(matricula)

    notas = Nota.objects.filter(
        alumno=alumno
    ).select_related(
        'evaluacion',
        'evaluacion__carga',
        'evaluacion__carga__asignatura'
    ).order_by('evaluacion__carga__asignatura__nombre_asignatura', 'evaluacion__fecha')

    promedio = notas.aggregate(p=Avg('valor_nota'))['p']
    promedio = round(promedio, 1) if promedio else 0

    total_evaluaciones = notas.count()

    promedios_por_asignatura = notas.values(
        'evaluacion__carga__asignatura__nombre_asignatura'
    ).annotate(promedio=Avg('valor_nota'))

    asignaturas_aprobadas = sum(
        1 for a in promedios_por_asignatura if a['promedio'] >= 4.0
    )

    notas_por_asignatura = []
    for asignatura in asignaturas:
        notas_asignatura = list(notas.filter(
            evaluacion__carga__asignatura=asignatura
        ))
        promedio_asignatura = (
            round(
                float(sum(nota.valor_nota for nota in notas_asignatura) / len(notas_asignatura)),
                1,
            )
            if notas_asignatura
            else 0
        )

        notas_por_asignatura.append({
            'asignatura': asignatura,
            'notas': notas_asignatura,
            'promedio': promedio_asignatura,
        })

    context = {
        'notas': notas,
        'notas_por_asignatura': notas_por_asignatura,
        'matricula': matricula,
        'promedio': promedio,
        'total_evaluaciones': total_evaluaciones,
        'asignaturas_aprobadas': asignaturas_aprobadas,
    }
    return render(request, 'colegio/panel_alumno_notas.html', context)


@login_required
def panel_alumno_asistencia(request):
    alumno = Alumno.objects.get(usuario=request.user)
    asignatura_id = request.GET.get("asignatura", "").strip()

    registros = Asistencia.objects.filter(
        alumno=alumno
    ).select_related(
        'carga__asignatura',
        'carga__docente'
    ).order_by('-fecha')

    asignaturas_asistencia = list(
        registros.order_by(
            'carga__asignatura__nombre_asignatura'
        ).values(
            'carga__asignatura_id',
            'carga__asignatura__nombre_asignatura',
        ).distinct()
    )

    if asignatura_id:
        registros = registros.filter(carga__asignatura_id=asignatura_id)

    # Conteos para las cards resumen
    total      = registros.count()
    presentes  = registros.filter(estado_asistencia__iexact='Presente').count()
    ausentes   = registros.filter(estado_asistencia__iexact='Ausente').count()
    justificados = registros.filter(estado_asistencia__iexact='Justificado').count()

    porcentaje = round((presentes / total * 100), 1) if total > 0 else 0

    context = {
        'alumno':       alumno,
        'registros':    registros,
        'total':        total,
        'presentes':    presentes,
        'ausentes':     ausentes,
        'justificados': justificados,
        'porcentaje':   porcentaje,
        'asignaturas_asistencia': asignaturas_asistencia,
        'asignatura_id': asignatura_id,
    }
    return render(request, 'colegio/panel_alumno_asistencia.html', context)


@login_required
def panel_alumno_perfil(request):
    alumno = Alumno.objects.select_related('usuario').get(usuario=request.user)

    # Asignaturas del curso en que está matriculado el alumno
    # Se obtiene via Matricula → Curso → CargaAcademica
    cargas = CargaAcademica.objects.filter(
        curso__matricula__alumno=alumno
    ).select_related(
        'curso', 'asignatura', 'docente', 'periodo'
    ).distinct()

    context = {
        'alumno': alumno,
        'cargas': cargas,
    }

    return render(request, 'colegio/panel_alumno_perfil.html', context)


# ============================================================
# PANEL APODERADO
# ============================================================

@login_required
def panel_apoderado(request):
    if request.user.tipo_usuario != 'APODERADO':
        return redireccionar_por_rol(request.user)

    try:
        apoderado = Apoderado.objects.get(usuario=request.user)
        relaciones = AlumnoApoderado.objects.filter(
            apoderado=apoderado
        ).select_related('alumno')

        alumnos = [r.alumno for r in relaciones]

        alumnos_info = []
        for alumno in alumnos:
            matricula = Matricula.objects.filter(
                alumno=alumno, estado='Activa'
            ).order_by('-fecha_matricula').first()

            promedio = Nota.objects.filter(alumno=alumno).aggregate(
                p=Avg('valor_nota')
            )['p']
            promedio = round(promedio, 1) if promedio else 0

            total_clases = Asistencia.objects.filter(alumno=alumno).count()
            presentes = Asistencia.objects.filter(
                alumno=alumno, estado_asistencia='Presente'
            ).count()
            asistencia_pct = round((presentes / total_clases) * 100) if total_clases > 0 else 0

            alumnos_info.append({
                'alumno': alumno,
                'curso': matricula.curso if matricula else None,
                'promedio': promedio,
                'asistencia_pct': asistencia_pct,
            })

        alertas = sum(1 for a in alumnos_info if 0 < a['promedio'] < 4.0)
        asistencia_promedio = round(
            sum(a['asistencia_pct'] for a in alumnos_info) / len(alumnos_info)
        ) if alumnos_info else 0

        ultimas_notas = Nota.objects.filter(
            alumno__in=alumnos
        ).select_related(
            'alumno',
            'evaluacion',
            'evaluacion__carga__asignatura'
        ).order_by('-fecha_registro')[:5]

    except Apoderado.DoesNotExist:
        apoderado = None
        alumnos_info = []
        alertas = 0
        asistencia_promedio = 0
        ultimas_notas = []

    return render(request, 'colegio/panel_apoderado.html', {
        'apoderado': apoderado,
        'alumnos_info': alumnos_info,
        'total_alumnos': len(alumnos_info),
        'asistencia_promedio': asistencia_promedio,
        'alertas': alertas,
        'ultimas_notas': ultimas_notas,
    })


@login_required
def panel_apoderado_estudiantes(request):
    if request.user.tipo_usuario != 'APODERADO':
        return redireccionar_por_rol(request.user)

    try:
        apoderado = Apoderado.objects.get(usuario=request.user)
        relaciones = AlumnoApoderado.objects.filter(
            apoderado=apoderado
        ).select_related('alumno')

        alumnos_info = []
        for r in relaciones:
            alumno = r.alumno
            matricula = Matricula.objects.filter(
                alumno=alumno, estado='Activa'
            ).order_by('-fecha_matricula').first()

            promedio = Nota.objects.filter(alumno=alumno).aggregate(
                p=Avg('valor_nota')
            )['p']
            promedio = round(promedio, 1) if promedio else 0

            total_clases = Asistencia.objects.filter(alumno=alumno).count()
            presentes = Asistencia.objects.filter(
                alumno=alumno, estado_asistencia='Presente'
            ).count()
            asistencia_pct = round((presentes / total_clases) * 100) if total_clases > 0 else 0

            alumnos_info.append({
                'alumno': alumno,
                'curso': matricula.curso if matricula else None,
                'promedio': promedio,
                'asistencia_pct': asistencia_pct,
                'parentesco': r.parentesco,
            })

    except Apoderado.DoesNotExist:
        alumnos_info = []

    return render(request, 'colegio/panel_apoderado_estudiantes.html', {
        'alumnos_info': alumnos_info,
    })


@login_required
def panel_apoderado_notas(request):
    if request.user.tipo_usuario != "APODERADO":
        return redireccionar_por_rol(request.user)

    try:
        apoderado = Apoderado.objects.get(usuario=request.user)
        relaciones = AlumnoApoderado.objects.filter(
            apoderado=apoderado
        ).select_related('alumno')

        alumnos = [r.alumno for r in relaciones]

        notas = Nota.objects.filter(
            alumno__in=alumnos
        ).select_related(
            'alumno',
            'evaluacion',
            'evaluacion__carga__asignatura'
        ).order_by('-fecha_registro')

    except Apoderado.DoesNotExist:
        notas = []

    return render(request, "colegio/panel_apoderado_notas.html", {
        'notas': notas,
    })


@login_required
def panel_apoderado_asistencia(request):
    if request.user.tipo_usuario != "APODERADO":
        return redireccionar_por_rol(request.user)

    try:
        apoderado = Apoderado.objects.get(usuario=request.user)
        alumnos = [r.alumno for r in AlumnoApoderado.objects.filter(
            apoderado=apoderado
        ).select_related('alumno')]

        registros = Asistencia.objects.filter(
            alumno__in=alumnos
        ).select_related(
            'alumno',
            'carga__asignatura'
        ).order_by('-fecha')

        total      = registros.count()
        presentes  = registros.filter(estado_asistencia__iexact='Presente').count()
        ausentes   = registros.filter(estado_asistencia__iexact='Ausente').count()
        justificados = registros.filter(estado_asistencia__iexact='Justificado').count()
        porcentaje = round((presentes / total * 100), 1) if total > 0 else 0

    except Apoderado.DoesNotExist:
        registros = []
        presentes = ausentes = justificados = porcentaje = 0

    return render(request, "colegio/panel_apoderado_asistencia.html", {
        'registros': registros,
        'porcentaje': porcentaje,
        'ausentes': ausentes,
        'justificados': justificados,
    })


@login_required
def panel_apoderado_pagos(request):
    """Panel de pagos del apoderado."""
    if request.user.tipo_usuario != "APODERADO":
        return redireccionar_por_rol(request.user)

    return render(request, "colegio/panel_apoderado_pagos.html")


@login_required
def panel_apoderado_perfil(request):
    if request.user.tipo_usuario != "APODERADO":
        return redireccionar_por_rol(request.user)

    try:
        apoderado = Apoderado.objects.select_related('usuario').get(usuario=request.user)
        relaciones = AlumnoApoderado.objects.filter(
            apoderado=apoderado
        ).select_related('alumno')
    except Apoderado.DoesNotExist:
        apoderado = None
        relaciones = []

    return render(request, "colegio/panel_apoderado_perfil.html", {
        'apoderado': apoderado,
        'relaciones': relaciones,
    })


def landing_cliente(request, slug_colegio):
    # InstitucionMiddleware ya resolvió el slug (404 si no existe o está inactiva).
    return render(request, "colegio/landing_demo.html", {
        "colegio": request.institucion
    })
# ============================================================
# CREAR PERSONAS (ADMIN) — Alumno / Apoderado
# ============================================================
@login_required
def registrar_alumno(request):
    """
    Registro interno del administrador.

    Esta vista sí crea:
    - Usuario Apoderado
    - Perfil Apoderado
    - Usuario Alumno
    - Perfil Alumno
    - Relación AlumnoApoderado
    """

    if not es_admin(request.user):
        return redireccionar_por_rol(request.user)

    if request.method == "POST":
        form = RegistroAlumnoApoderadoForm(request.POST)

        if form.is_valid():
            try:
                with transaction.atomic():
                    crear_alumno_apoderado_desde_data(form.cleaned_data)

                messages.success(
                    request,
                    "Alumno y apoderado registrados correctamente. Contraseña inicial: EduGestor@123"
                )
                return redirect("panel_admin_matriculas")

            except IntegrityError:
                form.add_error(
                    None,
                    "No se pudo completar el registro porque existe información duplicada."
                )

            except Exception as e:
                form.add_error(
                    None,
                    f"No se pudo completar el registro. Detalle: {e}"
                )

    else:
        form = RegistroAlumnoApoderadoForm()

    return render(request, "colegio/registrar_alumno.html", {
        "form": form
    })


# ============================================================
# API AUTOCOMPLETE
# ============================================================

def api_buscar_apoderados(request):
    """Busca apoderados por nombre o RUT."""
    query = request.GET.get('q', '').strip()
    
    if len(query) < 2:
        return JsonResponse({'apoderados': []})
    
    apoderados = Apoderado.objects.filter(
        Q(nombre_apoderado__icontains=query) |
        Q(apellido_apoderado__icontains=query) |
        Q(usuario__rut__icontains=query)
    ).values('id', 'nombre_apoderado', 'apellido_apoderado', 'usuario__rut')[:20]
    
    resultado = [
        {
            'id': a['id'],
            'nombre': f"{a['nombre_apoderado']} {a['apellido_apoderado']}",
            'rut': a['usuario__rut']
        }
        for a in apoderados
    ]
    
    return JsonResponse({'apoderados': resultado})


def api_buscar_docentes(request):
    """Busca docentes por nombre o RUT."""
    query = request.GET.get('q', '').strip()
    
    if len(query) < 2:
        return JsonResponse({'docentes': []})
    
    docentes = Docente.objects.filter(
        Q(nombre_docente__icontains=query) |
        Q(apellido_docente__icontains=query) |
        Q(usuario__rut__icontains=query)
    ).values('id', 'nombre_docente', 'apellido_docente', 'usuario__rut')[:20]
    
    resultado = [
        {
            'id': d['id'],
            'nombre': f"{d['nombre_docente']} {d['apellido_docente']}",
            'rut': d['usuario__rut']
        }
        for d in docentes
    ]
    
    return JsonResponse({'docentes': resultado})
