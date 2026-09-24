from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.crypto import get_random_string
from django.contrib import messages
from .models import (Institucion, Usuario, Alumno, Docente, Apoderado, AlumnoApoderado,
    Curso, Asignatura, PeriodoAcademico, Matricula,
    CargaAcademica, Evaluacion, Nota, Asistencia,SolicitudPostulacion)
from .forms import AlumnoAdminForm, DocenteAdminForm, ApoderadoAdminForm
# Register your models here.

@admin.register(Institucion)
class InstitucionAdmin(admin.ModelAdmin):
    list_display = ("nombre", "slug", "activa", "fecha_creacion")
    prepopulated_fields = {"slug": ("nombre",)}


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ('Datos adicionales', {
            'fields': ('institucion', 'tipo_usuario', 'rut')
        }),
    )

    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Datos adicionales', {
            'fields': ('institucion', 'tipo_usuario', 'rut')
        }),
    )

    list_display = ('username', 'rut', 'tipo_usuario', 'institucion', 'is_active')
    list_filter = UserAdmin.list_filter + ('institucion',)

# =========================
# ALUMNO (AUTO USER)
# =========================

@admin.register(Alumno)
class AlumnoAdmin(admin.ModelAdmin):
    form = AlumnoAdminForm

    list_display = (
        "nombre_alumno",
        "apellido_alumno",
        "rut_usuario",
        "username_usuario",
        "estado_alumno",
    )

    def rut_usuario(self, obj):
        return obj.usuario.rut

    def username_usuario(self, obj):
        return obj.usuario.username

    def save_model(self, request, obj, form, change):
        if not change:
            rut = form.cleaned_data["rut"]
            username = rut.replace(".", "").replace("-", "").lower()

            usuario = Usuario.objects.filter(rut=rut).first()

            if usuario:
                obj.usuario = usuario

                messages.warning(
                    request,
                    f"Ya existía un usuario con el RUT {rut}. Se vinculó automáticamente."
                )
            else:
                password_temporal = get_random_string(8)

                usuario = Usuario.objects.create_user(
                    username=username,
                    password=password_temporal,
                    rut=rut,
                    tipo_usuario="ALUMNO",
                    first_name=obj.nombre_alumno,
                    last_name=obj.apellido_alumno,
                )

                # La señal post_save ya crea el perfil del alumno.
                perfil_creado = Alumno.objects.get(usuario=usuario)
                obj.pk = perfil_creado.pk
                obj.usuario = usuario

                messages.success(
                    request,
                    f"Alumno creado. Usuario: {username} | Contraseña: {password_temporal}"
                )

        super().save_model(request, obj, form, change)


# =========================
# DOCENTE (AUTO USER)
# =========================
@admin.register(Docente)
class DocenteAdmin(admin.ModelAdmin):
    form = DocenteAdminForm

    list_display = (
        "nombre_docente",
        "apellido_docente",
        "rut_usuario",
        "username_usuario",
        "email_institucional",
    )

    def rut_usuario(self, obj):
        return obj.usuario.rut

    def username_usuario(self, obj):
        return obj.usuario.username

    def save_model(self, request, obj, form, change):
        if not change:
            rut = form.cleaned_data["rut"]
            username = rut.replace(".", "").replace("-", "").lower()
            password_temporal = get_random_string(8)

            usuario = Usuario.objects.create_user(
                username=username,
                password=password_temporal,
                rut=rut,
                tipo_usuario="DOCENTE",
                first_name=obj.nombre_docente,
                last_name=obj.apellido_docente,
                email=obj.email_institucional,
            )

            obj.usuario = usuario

            messages.success(
                request,
                f"Docente creado. Usuario: {username} | Contraseña temporal: {password_temporal}"
            )

        super().save_model(request, obj, form, change)

# =========================
# APODERADO (AUTO USER)
# =========================

@admin.register(Apoderado)
class ApoderadoAdmin(admin.ModelAdmin):
    form = ApoderadoAdminForm

    list_display = (
        "nombre_apoderado",
        "apellido_apoderado",
        "rut_usuario",
        "username_usuario",
        "email",
    )

    def rut_usuario(self, obj):
        return obj.usuario.rut

    def username_usuario(self, obj):
        return obj.usuario.username

    def save_model(self, request, obj, form, change):
        if not change:
            rut = form.cleaned_data["rut"]
            username = rut.replace(".", "").replace("-", "").lower()

            usuario = Usuario.objects.filter(rut=rut).first()

            if usuario:
                obj.usuario = usuario

                messages.success(
                    request,
                    f"Apoderado vinculado a usuario existente: {username}"
                )

            else:
                password_temporal = get_random_string(8)

                usuario = Usuario.objects.create_user(
                    username=username,
                    password=password_temporal,
                    rut=rut,
                    tipo_usuario="APODERADO",
                    first_name=obj.nombre_apoderado,
                    last_name=obj.apellido_apoderado,
                    email=obj.email,
                )

                obj.usuario = usuario

                messages.success(
                    request,
                    f"Apoderado creado. Usuario: {username} | Contraseña temporal: {password_temporal}"
                )

        super().save_model(request, obj, form, change)


admin.site.register(AlumnoApoderado)
admin.site.register(Curso)
admin.site.register(Asignatura)
admin.site.register(PeriodoAcademico)
admin.site.register(Matricula)
admin.site.register(CargaAcademica)
admin.site.register(Evaluacion)
admin.site.register(Nota)
admin.site.register(Asistencia)

# =========================
# REVISION PSOTULACION
# =========================

@admin.register(SolicitudPostulacion)
class SolicitudPostulacionAdmin(admin.ModelAdmin):
    list_display = (
        "nombre_alumno",
        "apellido_alumno",
        "rut_alumno",
        "nombre_apoderado",
        "email_apoderado",
        "estado",
        "fecha_solicitud",
    )

    list_filter = ("estado", "genero", "parentesco")
    search_fields = (
        "rut_alumno",
        "nombre_alumno",
        "apellido_alumno",
        "rut_apoderado",
        "nombre_apoderado",
        "email_apoderado",
    )
    readonly_fields = (
        "fecha_solicitud",
        "fecha_resolucion",
        "alumno_creado",
        "apoderado_creado",
        "procesada_por",
    )