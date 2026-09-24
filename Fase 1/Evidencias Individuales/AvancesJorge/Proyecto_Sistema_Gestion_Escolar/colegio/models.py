from django.db import models
from django.contrib.auth.models import  AbstractUser
from django.core.exceptions import ValidationError
from .validators import validar_rut_chileno
from .tenancy import (
    InstitucionCruzadaError,
    InstitucionManager,
    UsuarioManager,
    obtener_institucion_actual,
    resolver_institucion,
)
from django.db.models.signals import m2m_changed, post_save
from django.dispatch import receiver
import unicodedata


# Create your models here.

# ========================
# INSTITUCIÓN (MULTI-INQUILINO)
# ========================
class Institucion(models.Model):
    nombre = models.CharField(max_length=150)
    slug = models.SlugField(max_length=80, unique=True,
                            help_text="Identificador en la dirección propia del establecimiento.")
    activa = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "institución"
        verbose_name_plural = "instituciones"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class ModeloInstitucional(models.Model):
    """
    Base de todo dato que pertenece a una institución.

    PADRES_INSTITUCION nombra las FK desde las que se hereda la institución
    (una Nota la toma de su Evaluación); si no hay padre, se usa la institución
    activa del request. Guardar un registro cuyos padres son de otra
    institución lanza InstitucionCruzadaError.
    """
    PADRES_INSTITUCION = ()

    institucion = models.ForeignKey(
        Institucion, on_delete=models.PROTECT, related_name="+", editable=False,
    )

    objects = InstitucionManager()

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        resolver_institucion(self, self.PADRES_INSTITUCION)
        if self.institucion_id is None:
            raise InstitucionCruzadaError(
                f"No se pudo determinar la institución de {self.__class__.__name__}."
            )
        super().save(*args, **kwargs)


# ========================
# USUARIOS Y ROLES
# ========================
class Usuario(AbstractUser):
    TIPO_USUARIO = [
        ('ADMIN', 'Administrador'),
        ('DOCENTE', 'Docente'),
        ('ALUMNO', 'Alumno'),
        ('APODERADO', 'Apoderado'),
    ]

    tipo_usuario = models.CharField(max_length=20, choices=TIPO_USUARIO)

    # Nulo solo para superusuarios de plataforma (administran todas las instituciones).
    institucion = models.ForeignKey(
        Institucion, on_delete=models.PROTECT, related_name="usuarios",
        null=True, blank=True,
    )

    objects = UsuarioManager()

    # Único por institución: la misma persona puede estar en dos establecimientos.
    rut = models.CharField(
        max_length=12,
        validators=[validar_rut_chileno],
        help_text="Formato: 12.345.678-9"
    )

    class Meta(AbstractUser.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["institucion", "rut"],
                name="uq_usuario_institucion_rut",
            )
        ]

    def save(self, *args, **kwargs):
        resolver_institucion(self)
        if self.institucion_id is None and self.tipo_usuario:
            raise InstitucionCruzadaError(
                "Un usuario con rol debe pertenecer a una institución."
            )
        super().save(*args, **kwargs)

    def __str__(self):
        return self.username

# ========================
# PERSONAS
# ========================

#ALUMNO

class Alumno(ModeloInstitucional):
    PADRES_INSTITUCION = ("usuario",)

    usuario = models.OneToOneField(Usuario, on_delete=models.CASCADE)
    nombre_alumno = models.CharField(max_length=100)
    apellido_alumno = models.CharField(max_length=100)
    fecha_nacimiento = models.DateField()
    genero = models.CharField(max_length=20)
    estado_alumno = models.CharField(max_length=30)

    def __str__(self):
        return f"{self.nombre_alumno} {self.apellido_alumno}"
    
# DOCENTE

class Docente(ModeloInstitucional):
    PADRES_INSTITUCION = ("usuario",)

    usuario = models.OneToOneField(Usuario, on_delete=models.CASCADE)
    nombre_docente = models.CharField(max_length=100)
    apellido_docente = models.CharField(max_length=100)
    telefono = models.CharField(max_length=20, blank=True, null=True)
    email_institucional = models.EmailField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["institucion", "email_institucional"],
                name="uq_docente_institucion_email",
            )
        ]

    def __str__(self):
        return f"{self.nombre_docente} {self.apellido_docente}"


class Apoderado(ModeloInstitucional):
    PADRES_INSTITUCION = ("usuario",)

    usuario = models.OneToOneField(Usuario, on_delete=models.CASCADE)
    nombre_apoderado = models.CharField(max_length=100)
    apellido_apoderado = models.CharField(max_length=100)
    direccion = models.CharField(max_length=255, blank=True, null=True)
    telefono = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["institucion", "email"],
                name="uq_apoderado_institucion_email",
            )
        ]

    def __str__(self):
        return f"{self.nombre_apoderado} {self.apellido_apoderado}"


class AlumnoApoderado(ModeloInstitucional):
    PADRES_INSTITUCION = ("alumno", "apoderado")

    alumno = models.ForeignKey(Alumno, on_delete=models.CASCADE)
    apoderado = models.ForeignKey(Apoderado, on_delete=models.CASCADE)
    parentesco = models.CharField(max_length=50)
    is_principal = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['alumno', 'apoderado'],
                name='uq_alumno_apoderado'
            )
        ]

    def __str__(self):
        return f"{self.alumno} - {self.apoderado}"

# ========================
# POSTULACION
# ========================
class SolicitudPostulacion(ModeloInstitucional):
    ESTADO_CHOICES = [
        ("PENDIENTE", "Pendiente"),
        ("APROBADA", "Aprobada"),
        ("RECHAZADA", "Rechazada"),
    ]

    # Datos del alumno
    rut_alumno = models.CharField(max_length=12)
    rut_alumno_normalizado = models.CharField(max_length=12, db_index=True)
    nombre_alumno = models.CharField(max_length=100)
    apellido_alumno = models.CharField(max_length=100)
    fecha_nacimiento = models.DateField()
    genero = models.CharField(max_length=20)

    # Curso al que postula
    CICLO_KINDER = "KINDER"
    CICLO_BASICA = "BASICA"
    CICLO_MEDIA = "MEDIA"

    CICLO_POSTULACION_CHOICES = [
        (CICLO_KINDER, "Kinder"),
        (CICLO_BASICA, "Enseñanza Básica"),
        (CICLO_MEDIA, "Enseñanza Media"),
    ]

    ciclo_postulacion = models.CharField(
        max_length=10,
        choices=CICLO_POSTULACION_CHOICES,
        blank=True,
        null=True,
        verbose_name="Ciclo al que postula"
    )

    nivel_postulacion = models.PositiveSmallIntegerField(
        blank=True,
        null=True,
        verbose_name="Nivel al que postula"
    )

    # Datos del apoderado
    rut_apoderado = models.CharField(max_length=12)
    rut_apoderado_normalizado = models.CharField(max_length=12, db_index=True)
    nombre_apoderado = models.CharField(max_length=100)
    apellido_apoderado = models.CharField(max_length=100)
    direccion = models.CharField(max_length=255, blank=True, null=True)
    telefono = models.CharField(max_length=20, blank=True, null=True)
    email_apoderado = models.EmailField()

    # Relación
    parentesco = models.CharField(max_length=50)
    is_principal = models.BooleanField(default=True)

    # Estado de la solicitud
    estado = models.CharField(
        max_length=20,
        choices=ESTADO_CHOICES,
        default="PENDIENTE"
    )

    fecha_solicitud = models.DateTimeField(auto_now_add=True)
    fecha_resolucion = models.DateTimeField(blank=True, null=True)

    observacion_admin = models.TextField(blank=True, null=True)

    procesada_por = models.ForeignKey(
        Usuario,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="postulaciones_procesadas"
    )

    alumno_creado = models.ForeignKey(
        Alumno,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="solicitudes_postulacion"
    )

    apoderado_creado = models.ForeignKey(
        Apoderado,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="solicitudes_postulacion"
    )

    class Meta:
        ordering = ["-fecha_solicitud"]
        indexes = [
            models.Index(fields=["estado"]),
            models.Index(fields=["rut_alumno_normalizado"]),
            models.Index(fields=["rut_apoderado_normalizado"]),
        ]

    def __str__(self):
        return f"{self.nombre_alumno} {self.apellido_alumno} - {self.estado}"

# ========================
# ACADÉMICO
# ========================
class Curso(ModeloInstitucional):
    PADRES_INSTITUCION = ("profesor_jefe",)

    CICLO_KINDER = 'KINDER'
    CICLO_BASICA = 'BASICA'
    CICLO_MEDIA = 'MEDIA'

    CICLO_CHOICES = [
        (CICLO_KINDER, 'Kinder'),
        (CICLO_BASICA, 'Enseñanza Básica'),
        (CICLO_MEDIA, 'Enseñanza Media'),
    ]

    NIVELES_POR_CICLO = {
        CICLO_KINDER: (1, 1),
        CICLO_BASICA: (1, 8),
        CICLO_MEDIA: (1, 4),
    }

    nivel = models.PositiveSmallIntegerField()
    seccion = models.CharField(max_length=2)
    ciclo = models.CharField(max_length=10, choices=CICLO_CHOICES)
    estado_curso = models.BooleanField(default=True)
    profesor_jefe = models.ForeignKey(
        Docente,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cursos_jefatura",
    )

    @classmethod
    def normalizar_ciclo(cls, ciclo):
        valor = str(ciclo or "").strip()
        valor = unicodedata.normalize("NFKD", valor).encode("ascii", "ignore").decode("ascii")
        valor = valor.upper().replace("ENSENANZA", "").strip()
        valor = " ".join(valor.split())

        aliases = {
            "KINDER": cls.CICLO_KINDER,
            "PARVULARIO": cls.CICLO_KINDER,
            "PRE KINDER": cls.CICLO_KINDER,
            "PRE-KINDER": cls.CICLO_KINDER,
            "BASICA": cls.CICLO_BASICA,
            "BASICO": cls.CICLO_BASICA,
            "MEDIA": cls.CICLO_MEDIA,
            "MEDIO": cls.CICLO_MEDIA,
        }
        return aliases.get(valor, valor)

    @classmethod
    def validar_nivel_por_ciclo(cls, ciclo, nivel):
        ciclo = cls.normalizar_ciclo(ciclo)
        if ciclo not in cls.NIVELES_POR_CICLO:
            return "Selecciona un ciclo académico válido."

        minimo, maximo = cls.NIVELES_POR_CICLO[ciclo]
        try:
            nivel = int(nivel)
        except (TypeError, ValueError):
            return "Ingresa un nivel numérico válido."

        if not minimo <= nivel <= maximo:
            if ciclo == cls.CICLO_KINDER:
                return "Kinder solo permite el nivel 1."
            nombre_ciclo = dict(cls.CICLO_CHOICES)[ciclo]
            return f"{nombre_ciclo} permite niveles desde {minimo} hasta {maximo}."

        return None

    @property
    def nivel_label(self):
        if self.ciclo == self.CICLO_KINDER:
            return "Kinder"
        return f"{self.nivel}°"

    def clean(self):
        super().clean()
        self.ciclo = self.normalizar_ciclo(self.ciclo)
        self.seccion = (self.seccion or "").strip().upper()

        if self.ciclo and self.nivel is not None:
            error = self.validar_nivel_por_ciclo(self.ciclo, self.nivel)
            if error:
                raise ValidationError({"nivel": error})

    def __str__(self):
        if self.ciclo == self.CICLO_KINDER:
            return f"Kinder {self.seccion}"

        ciclo_str = "Básico" if self.ciclo == self.CICLO_BASICA else "Medio"
        return f"{self.nivel}° {ciclo_str} {self.seccion}"


class Asignatura(ModeloInstitucional):
    PADRES_INSTITUCION = ("curso",)

    ESTADO_CHOICES = [
        (True, 'Activa'),
        (False, 'En Revisión'),
    ]

    nombre_asignatura = models.CharField(max_length=100, verbose_name="Nombre")
    descripcion = models.TextField(blank=True, null=True, verbose_name="Descripción")
    
    # 1. Relación con Curso (1:N): Una asignatura pertenece a un único Curso
    curso = models.ForeignKey(
        Curso, 
        on_delete=models.CASCADE, 
        related_name='asignaturas',
        verbose_name="Curso"
    )
    
    # 2. Relación con Docente (N:N): Una asignatura puede tener 1 o más profesores
    docentes = models.ManyToManyField(
        Docente, 
        blank=True, 
        related_name='asignaturas',
        verbose_name="Docentes a Cargo"
    )
    
    estado_asignatura = models.BooleanField(default=True, choices=ESTADO_CHOICES, verbose_name="Estado")

    def __str__(self):
        return f"{self.nombre_asignatura} ({self.curso})"
# ========================
class PeriodoAcademico(ModeloInstitucional):
    anio = models.PositiveIntegerField()
    semestre = models.PositiveSmallIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['institucion', 'anio', 'semestre'],
                name='uq_periodo_institucion_anio_semestre'
            )
        ]

    def __str__(self):
        return f"{self.anio} - Semestre {self.semestre}"


class Matricula(ModeloInstitucional):
    PADRES_INSTITUCION = ("periodo", "alumno", "curso")

    periodo = models.ForeignKey(PeriodoAcademico, on_delete=models.CASCADE)
    alumno = models.ForeignKey(Alumno, on_delete=models.CASCADE)
    curso = models.ForeignKey(Curso, on_delete=models.CASCADE)
    apoderados = models.ManyToManyField(Apoderado, blank=True, related_name='matriculas')
    estado = models.CharField(max_length=20, default="Activa")
    fecha_matricula = models.DateField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['periodo', 'alumno'],
                name='uq_periodo_alumno'
            )
        ]

    def __str__(self):
        return f"{self.alumno} - {self.curso} - {self.periodo}"

class CargaAcademica(ModeloInstitucional):
    PADRES_INSTITUCION = ("curso", "asignatura", "periodo", "docente")

    curso = models.ForeignKey(Curso, on_delete=models.CASCADE)
    asignatura = models.ForeignKey(Asignatura, on_delete=models.CASCADE)
    periodo = models.ForeignKey(PeriodoAcademico, on_delete=models.CASCADE)
    docente = models.ForeignKey(Docente, on_delete=models.CASCADE)
    

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['curso', 'asignatura', 'periodo', 'docente'],
                name='uq_carga_academica'
            )
        ]

    def __str__(self):
        return f"{self.curso} - {self.asignatura} - {self.docente}"
    



@receiver(post_save, sender=Usuario)
def crear_perfil_segun_rol(sender, instance, created, **kwargs):
    if not created:
        return
    if instance.tipo_usuario == 'DOCENTE':
        Docente.objects.get_or_create(
            usuario=instance,
            defaults={
                'nombre_docente': instance.first_name or instance.username,
                'apellido_docente': instance.last_name or '',
                'email_institucional': instance.email or f'{instance.username}@colegio.cl',
            }
        )
    elif instance.tipo_usuario == 'ALUMNO':
        Alumno.objects.get_or_create(
            usuario=instance,
            defaults={
                'nombre_alumno': instance.first_name or instance.username,
                'apellido_alumno': instance.last_name or '',
                'fecha_nacimiento': '2000-01-01',
                'genero': 'No especificado',
                'estado_alumno': 'Activo',
            }
        )
    elif instance.tipo_usuario == 'APODERADO':
        Apoderado.objects.get_or_create(
            usuario=instance,
            defaults={
                'nombre_apoderado': instance.first_name or instance.username,
                'apellido_apoderado': instance.last_name or '',
                'email': instance.email if instance.email else f'{instance.username}@apoderado.edugestor.cl',
            }
        )


# ========================
# EVALUACIONES
# ========================
class Evaluacion(ModeloInstitucional):
    PADRES_INSTITUCION = ("carga",)

    carga = models.ForeignKey(CargaAcademica, on_delete=models.CASCADE)
    nombre_evaluacion = models.CharField(max_length=100)
    tipo_evaluacion = models.CharField(max_length=50)
    porcentaje = models.DecimalField(max_digits=5, decimal_places=2)
    fecha = models.DateField()
    numero_evaluacion = models.PositiveSmallIntegerField()

    def __str__(self):
        return self.nombre_evaluacion


class Nota(ModeloInstitucional):
    PADRES_INSTITUCION = ("evaluacion", "alumno")

    evaluacion = models.ForeignKey(Evaluacion, on_delete=models.CASCADE)
    alumno = models.ForeignKey(Alumno, on_delete=models.CASCADE)
    valor_nota = models.DecimalField(max_digits=4, decimal_places=2)
    observacion = models.TextField(blank=True, null=True)
    fecha_registro = models.DateField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['evaluacion', 'alumno'],
                name='uq_nota_evaluacion_alumno'
            )
        ]

    def __str__(self):
        return f"{self.alumno} - {self.valor_nota}"

# ========================
# ASISTENCIA
# ========================
class Asistencia(ModeloInstitucional):
    PADRES_INSTITUCION = ("alumno", "carga")

    alumno = models.ForeignKey(Alumno, on_delete=models.CASCADE)
    carga = models.ForeignKey(CargaAcademica, on_delete=models.CASCADE)
    fecha = models.DateField()
    estado_asistencia = models.CharField(max_length=20)
    observacion = models.TextField(blank=True, null=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['alumno', 'carga', 'fecha'],
                name='uq_asistencia_alumno_carga_fecha'
            )
        ]

    def __str__(self):
        return f"{self.alumno} - {self.fecha}"
    

# ========================
# INTEGRIDAD ENTRE INSTITUCIONES EN RELACIONES N:N
# ========================
@receiver(m2m_changed, sender=Asignatura.docentes.through)
@receiver(m2m_changed, sender=Matricula.apoderados.through)
def validar_m2m_misma_institucion(sender, instance, action, reverse, model, pk_set, **kwargs):
    if action != "pre_add" or not pk_set:
        return
    # model es el lado agregado; instance el lado dueño de la relación.
    ajenos = model._base_manager.filter(pk__in=pk_set).exclude(institucion_id=instance.institucion_id)
    if ajenos.exists():
        raise InstitucionCruzadaError(
            f"No se puede relacionar {instance.__class__.__name__} con {model.__name__} de otra institución."
        )


# ========================
# ASISTENTE IA DOCENTE
# ========================
class InstrumentoIA(ModeloInstitucional):
    """
    Prueba, rúbrica o material de estudio generado con IA.

    contenido_ia guarda el borrador tal como lo entregó el modelo y contenido
    la versión editada por el docente. Al aprobar se calcula qué porcentaje del
    texto corrigió el docente: es la medida de calidad del asistente.
    """
    PADRES_INSTITUCION = ("docente", "carga")

    TIPO_PRUEBA = "PRUEBA"
    TIPO_RUBRICA = "RUBRICA"
    TIPO_MATERIAL = "MATERIAL"
    TIPO_CHOICES = [
        (TIPO_PRUEBA, "Prueba"),
        (TIPO_RUBRICA, "Rúbrica"),
        (TIPO_MATERIAL, "Material de estudio"),
    ]
    ESTADO_BORRADOR = "BORRADOR"
    ESTADO_APROBADO = "APROBADO"
    ESTADO_CHOICES = [
        (ESTADO_BORRADOR, "Borrador"),
        (ESTADO_APROBADO, "Aprobado"),
    ]

    docente = models.ForeignKey(Docente, on_delete=models.CASCADE, related_name="instrumentos_ia")
    carga = models.ForeignKey(CargaAcademica, on_delete=models.CASCADE, related_name="instrumentos_ia")
    tipo = models.CharField(max_length=10, choices=TIPO_CHOICES)
    titulo = models.CharField(max_length=200)
    objetivo = models.TextField(blank=True, help_text="Objetivo de Aprendizaje (OA) al que apunta.")
    parametros = models.JSONField(default=dict, blank=True)
    contenido_ia = models.JSONField()
    contenido = models.JSONField()
    estado = models.CharField(max_length=10, choices=ESTADO_CHOICES, default=ESTADO_BORRADOR)
    porcentaje_corregido = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_aprobacion = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-fecha_creacion"]

    def __str__(self):
        return f"{self.get_tipo_display()}: {self.titulo}"


class CorreccionPrueba(ModeloInstitucional):
    """
    Corrección de una prueba de IA respondida por un alumno.

    respuestas guarda, por pregunta, la alternativa marcada (0-3 o null), lo que
    leyó la IA y si el docente la ajustó. Las imágenes de la hoja no se guardan.
    """
    PADRES_INSTITUCION = ("instrumento", "alumno")

    instrumento = models.ForeignKey(InstrumentoIA, on_delete=models.CASCADE, related_name="correcciones")
    alumno = models.ForeignKey(Alumno, on_delete=models.SET_NULL, null=True, blank=True,
                               related_name="correcciones_prueba")
    respuestas = models.JSONField()
    correctas = models.PositiveSmallIntegerField()
    total = models.PositiveSmallIntegerField()
    nota = models.DecimalField(max_digits=3, decimal_places=1)
    leida_con_ia = models.BooleanField(default=False)
    ajustes_docente = models.PositiveSmallIntegerField(
        default=0, help_text="Respuestas que el docente cambió respecto de la lectura de la IA.")
    nota_registrada = models.ForeignKey(Nota, on_delete=models.SET_NULL, null=True, blank=True,
                                        related_name="+")
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-fecha"]

    def __str__(self):
        return f"{self.instrumento} — {self.alumno or 'sin alumno'}: {self.nota}"
