from django import forms
from django.db.models import Q
from .models import Usuario, Alumno, Docente, Apoderado, AlumnoApoderado, Matricula, Curso, PeriodoAcademico, Asignatura,SolicitudPostulacion
from .validators import validar_rut_chileno


class AlumnoAdminForm(forms.ModelForm):
    rut = forms.CharField(
        max_length=12,
        label="RUT",
        help_text="Formato: 12.345.678-9"
    )

    fecha_nacimiento = forms.DateField(
        input_formats=["%d-%m-%Y", "%Y-%m-%d"],
        widget=forms.DateInput(
            format="%d-%m-%Y",
            attrs={
                "placeholder": "DD-MM-AAAA"
            }
        )
    )

    class Meta:
        model = Alumno
        fields = [
            "rut",
            "nombre_alumno",
            "apellido_alumno",
            "fecha_nacimiento",
            "genero",
            "estado_alumno",
        ]

    def clean_rut(self):
        rut = self.cleaned_data["rut"].strip().upper()
        validar_rut_chileno(rut)

        if Usuario.objects.filter(rut=rut).exists() or username_ocupado(normalizar_rut_para_username(rut)):
            raise forms.ValidationError("Este RUT ya está registrado.")

        return rut


class DocenteAdminForm(forms.ModelForm):
    rut = forms.CharField(
        max_length=12,
        label="RUT",
        help_text="Formato: 12.345.678-9"
    )

    class Meta:
        model = Docente
        fields = [
            "rut",
            "nombre_docente",
            "apellido_docente",
            "telefono",
            "email_institucional",
        ]

    def clean_rut(self):
        rut = self.cleaned_data["rut"].strip().upper()
        validar_rut_chileno(rut)

        if Usuario.objects.filter(rut=rut).exists() or username_ocupado(normalizar_rut_para_username(rut)):
            raise forms.ValidationError("Este RUT ya está registrado.")

        return rut


class ApoderadoAdminForm(forms.ModelForm):
    rut = forms.CharField(
        max_length=12,
        label="RUT",
        help_text="Formato: 12.345.678-9"
    )

    class Meta:
        model = Apoderado
        fields = [
            "rut",
            "nombre_apoderado",
            "apellido_apoderado",
            "direccion",
            "telefono",
            "email",
        ]

    def clean_rut(self):
        rut = self.cleaned_data["rut"].strip().upper()
        validar_rut_chileno(rut)

        usuario = Usuario.objects.filter(rut=rut).first()

        # Si ya existe usuario, solo es válido si es APODERADO y no tiene perfil aún
        if usuario:
            if usuario.tipo_usuario != 'APODERADO':
                raise forms.ValidationError("Este RUT pertenece a un usuario que no es Apoderado.")
            if Apoderado.objects.filter(usuario=usuario).exists():
                raise forms.ValidationError("Este apoderado ya tiene perfil creado.")
        elif username_ocupado(normalizar_rut_para_username(rut)):
            raise forms.ValidationError("Este RUT ya está registrado.")

        return rut

class MatriculaAdminForm(forms.ModelForm):
    """Formulario para crear nueva matrícula usando referencia de postulación."""

    ESTADO_CHOICES = [
        ("Activa", "Activa"),
        ("Inactiva", "Inactiva"),
        ("Retirado", "Retirado"),
    ]

    estado = forms.ChoiceField(
        choices=ESTADO_CHOICES,
        label="Estado",
        initial="Activa",
        widget=forms.Select(attrs={
            "class": "form-control"
        })
    )

    class Meta:
        model = Matricula
        fields = ["alumno", "curso", "periodo", "estado"]
        labels = {
            "alumno": "Alumno",
            "curso": "Curso",
            "periodo": "Período Académico",
            "estado": "Estado",
        }
        widgets = {
            "alumno": forms.Select(attrs={"class": "form-control"}),
            "curso": forms.Select(attrs={"class": "form-control"}),
            "periodo": forms.Select(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, alumno_id=None, **kwargs):
        super().__init__(*args, **kwargs)

        self.postulacion_referencia = None

        alumnos_matriculados = Matricula.objects.values_list("alumno_id", flat=True)

        self.fields["alumno"].queryset = Alumno.objects.select_related(
            "usuario"
        ).exclude(
            id__in=alumnos_matriculados
        ).order_by(
            "apellido_alumno",
            "nombre_alumno"
        )

        self.fields["periodo"].queryset = PeriodoAcademico.objects.all().order_by(
            "-anio",
            "-semestre"
        )

        self.fields["curso"].queryset = Curso.objects.filter(
            estado_curso=True
        ).order_by(
            "ciclo",
            "nivel",
            "seccion"
        )

        if alumno_id:
            alumno = Alumno.objects.select_related("usuario").filter(
                pk=alumno_id
            ).first()

            if alumno:
                self.fields["alumno"].initial = alumno.pk
                self.fields["alumno"].disabled = True

                self.postulacion_referencia = SolicitudPostulacion.objects.filter(
                    Q(alumno_creado=alumno) |
                    Q(rut_alumno_normalizado__iexact=alumno.usuario.username) |
                    Q(rut_alumno__iexact=alumno.usuario.rut),
                    estado="APROBADA"
                ).order_by("-fecha_solicitud").first()

                if (
                    self.postulacion_referencia
                    and self.postulacion_referencia.ciclo_postulacion
                    and self.postulacion_referencia.nivel_postulacion
                ):
                    self.fields["curso"].queryset = Curso.objects.filter(
                        ciclo=self.postulacion_referencia.ciclo_postulacion,
                        nivel=self.postulacion_referencia.nivel_postulacion,
                        estado_curso=True
                    ).order_by("seccion")

    def clean(self):
        cleaned_data = super().clean()

        curso = cleaned_data.get("curso")

        if self.postulacion_referencia and curso:
            ciclo_postulacion = self.postulacion_referencia.ciclo_postulacion
            nivel_postulacion = self.postulacion_referencia.nivel_postulacion

            if curso.ciclo != ciclo_postulacion or curso.nivel != nivel_postulacion:
                self.add_error(
                    "curso",
                    "El curso seleccionado no coincide con el ciclo y nivel de la postulación aprobada."
                )

        return cleaned_data

class MatriculaAdminFormEdit(forms.ModelForm):
    """Formulario para editar matrícula (con búsqueda de apoderados)."""
    
    ESTADO_CHOICES = [
        ("Activa", "Activa"),
        ("Inactiva", "Inactiva"),
        ("Retirado", "Retirado"),
    ]

    estado = forms.ChoiceField(
        choices=ESTADO_CHOICES,
        label="Estado",
        widget=forms.Select(attrs={
            "class": "form-control"
        })
    )

    class Meta:
        model = Matricula
        fields = ["alumno", "curso", "periodo", "apoderados", "estado"]
        labels = {
            "alumno": "Alumno",
            "curso": "Curso",
            "periodo": "Período Académico",
            "apoderados": "Apoderados",
            "estado": "Estado",
        }
        widgets = {
            "alumno": forms.Select(attrs={
                "class": "form-control"
            }),
            "curso": forms.Select(attrs={
                "class": "form-control"
            }),
            "periodo": forms.Select(attrs={
                "class": "form-control"
            }),
            "apoderados": forms.CheckboxSelectMultiple(attrs={
                "class": "apoderado-checkbox",
                "style": "display:none;"
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # El alumno no se cambia en edición.
        self.fields["alumno"].disabled = True

        self.fields["curso"].queryset = Curso.objects.filter(
            estado_curso=True
        ).order_by("ciclo", "nivel", "seccion")

        self.fields["periodo"].queryset = PeriodoAcademico.objects.all().order_by(
            "-anio",
            "-semestre"
        )

        self.fields["apoderados"].queryset = Apoderado.objects.all().order_by(
            "apellido_apoderado",
            "nombre_apoderado"
        )

class MatriculaForm(forms.Form):
    rut_alumno = forms.CharField(max_length=12)
    nombre_alumno = forms.CharField(max_length=100)
    apellido_alumno = forms.CharField(max_length=100)
    fecha_nacimiento = forms.DateField(
        input_formats=["%d-%m-%Y", "%Y-%m-%d"],
        widget=forms.DateInput(
            format="%d-%m-%Y",
            attrs={"placeholder": "DD-MM-AAAA"}
        )
    )
    genero = forms.CharField(max_length=20)

    rut_apoderado = forms.CharField(max_length=12)
    nombre_apoderado = forms.CharField(max_length=100)
    apellido_apoderado = forms.CharField(max_length=100)
    telefono_apoderado = forms.CharField(max_length=20)
    correo_apoderado = forms.EmailField(required=False)
    parentesco = forms.CharField(max_length=50)

    curso = forms.ModelChoiceField(queryset=Curso.objects.all())
    periodo = forms.ModelChoiceField(queryset=PeriodoAcademico.objects.all())


class CursoForm(forms.ModelForm):
    profesor_jefe = forms.ModelChoiceField(
        queryset=Docente.objects.all().order_by("apellido_docente", "nombre_docente"),
        required=False,
        label="Profesor Jefe",
        widget=forms.HiddenInput(),
    )

    class Meta:
        model = Curso
        fields = ['ciclo', 'nivel', 'seccion', 'estado_curso', 'profesor_jefe']
        labels = {
            'ciclo': 'Ciclo Académico',
            'nivel': 'Nivel',
            'seccion': 'Letra / Sección',
            'estado_curso': '¿Curso Activo?',
        }
        help_texts = {
            'nivel': 'Kinder: 1. Enseñanza Básica: 1 a 8. Enseñanza Media: 1 a 4.',
        }

    def clean(self):
        cleaned_data = super().clean()
        ciclo = cleaned_data.get('ciclo')
        nivel = cleaned_data.get('nivel')
        seccion = cleaned_data.get('seccion')

        if ciclo:
            ciclo = Curso.normalizar_ciclo(ciclo)
            cleaned_data['ciclo'] = ciclo

        if ciclo and nivel is not None:
            error_nivel = Curso.validar_nivel_por_ciclo(ciclo, nivel)
            if error_nivel:
                self.add_error('nivel', error_nivel)

        if ciclo and nivel is not None and seccion:
            seccion = seccion.strip().upper()
            cleaned_data['seccion'] = seccion

            queryset = Curso.objects.filter(ciclo=ciclo, nivel=nivel, seccion=seccion)
            
            if self.instance and self.instance.pk:
                queryset = queryset.exclude(pk=self.instance.pk)
                
            if queryset.exists():
                self.add_error('nivel', f"Inconsistencia: El curso {nivel}° {ciclo} {seccion} ya se encuentra registrado.")
                
        return cleaned_data


# ============================================================
# FORMULARIO DE ASIGNATURA AJUSTADO AL NUEVO MODELO ERD
# ============================================================
class AsignaturaForm(forms.ModelForm):
    class Meta:
        model = Asignatura
        # Incluimos los nuevos campos requeridos y el estado
        fields = ['nombre_asignatura', 'descripcion', 'curso', 'docentes', 'estado_asignatura']
        labels = {
            'nombre_asignatura': 'Nombre de la Asignatura',
            'descripcion': 'Descripción',
            'curso': 'Curso Asociado',
            'docentes': 'Docente(s) a Cargo',
            'estado_asignatura': 'Estado',
        }
        help_texts = {
            'docentes': 'Marca o desmarca docentes. Si una asignacion ya tiene historial, usa un reemplazo para conservarlo.',
        }
        widgets = {
            'nombre_asignatura': forms.TextInput(attrs={
                'class': 'form-control', 
                'placeholder': 'Ej. Matemáticas, Lenguaje, Historia...'
            }),
            'descripcion': forms.Textarea(attrs={
                'class': 'form-control', 
                'rows': 3, 
                'placeholder': 'Añade un resumen breve o descripción de la asignatura...'
            }),
            'curso': forms.Select(attrs={
                'class': 'form-control'
            }),
            'docentes': forms.CheckboxSelectMultiple(attrs={
                'class': 'docente-checkbox'
            }),
            'estado_asignatura': forms.Select(attrs={
                'class': 'form-control'
            }),

        }
class DocenteAdminForm(forms.ModelForm):
    rut = forms.CharField(
        max_length=12,
        label="RUT",
        help_text="Formato: 12.345.678-9",
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '12.345.678-9'})
    )
    first_name = forms.CharField(max_length=150, label="Nombre", widget=forms.TextInput(attrs={'class': 'form-control'}))
    last_name = forms.CharField(max_length=150, label="Apellido", widget=forms.TextInput(attrs={'class': 'form-control'}))

    class Meta:
        model = Docente
        fields = ["rut", "telefono", "email_institucional"]
        widgets = {
            'telefono': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+569... '}),
            'email_institucional': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'ejemplo@colegio.cl'}),
        }

    def clean_rut(self):
        rut = self.cleaned_data["rut"].strip().upper()
        validar_rut_chileno(rut)
        return rut
    
class DocenteForm(forms.ModelForm):
    # Campo personalizado para capturar el RUT del Usuario asociado
    rut = forms.CharField(
        max_length=12,
        label="RUT",
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '12.345.678-9'})
    )
    
    class Meta:
        model = Docente
        # Solo listamos los campos que pertenecen estrictamente al modelo Docente
        fields = ['nombre_docente', 'apellido_docente', 'email_institucional', 'telefono']
        widgets = {
            'nombre_docente': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: Carlos'}),
            'apellido_docente': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: Muñoz'}),
            'email_institucional': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'carlos.munoz@colegio.cl'}),
            'telefono': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+56912345678'}),
        }

    def clean_rut(self):
        rut = self.cleaned_data.get('rut', '').strip().upper()
        validar_rut_chileno(rut)  # Aplica tu validador personalizado
        return rut
    
    # =========================
    # FORMULARIO REGISTRO ALUMNO
    # =========================
def username_ocupado(username):
    """
    El username (derivado del RUT) aún es único en toda la plataforma, así que
    se revisa sin el filtro por institución. Deja de ser necesario cuando el
    acceso se resuelva por institución.
    """
    return Usuario._base_manager.filter(username__iexact=username).exists()


def normalizar_rut_para_username(rut):
    """
    Convierte el RUT en username.
    Ejemplo:
    12.345.678-9 -> 123456789
    11.111.111-K -> 11111111k
    """
    if not rut:
        return ""

    return (
        rut.strip()
        .replace(".", "")
        .replace("-", "")
        .replace(" ", "")
        .lower()
    )


GENERO_CHOICES = [
    ("", "Seleccione género"),
    ("Masculino", "Masculino"),
    ("Femenino", "Femenino"),
    ("Otro", "Otro"),
    ("No especificado", "No especificado"),
]


PARENTESCO_CHOICES = [
    ("", "Seleccione parentesco"),
    ("Madre", "Madre"),
    ("Padre", "Padre"),
    ("Abuelo/a", "Abuelo/a"),
    ("Tío/a", "Tío/a"),
    ("Hermano/a", "Hermano/a"),
    ("Tutor legal", "Tutor legal"),
    ("Otro", "Otro"),
]


class BaseAlumnoApoderadoForm(forms.Form):
    # =========================
    # DATOS DEL ALUMNO
    # =========================
    rut_alumno = forms.CharField(
        label="RUT del alumno",
        max_length=12,
        validators=[validar_rut_chileno],
        widget=forms.TextInput(attrs={
            "placeholder": "Ej: 12.345.678-9"
        })
    )

    nombre_alumno = forms.CharField(
        label="Nombre del alumno",
        max_length=100,
        widget=forms.TextInput(attrs={
            "placeholder": "Ingrese el nombre del alumno"
        })
    )

    apellido_alumno = forms.CharField(
        label="Apellido del alumno",
        max_length=100,
        widget=forms.TextInput(attrs={
            "placeholder": "Ingrese el apellido del alumno"
        })
    )

    fecha_nacimiento = forms.DateField(
        label="Fecha de nacimiento",
        input_formats=["%Y-%m-%d"],
        widget=forms.DateInput(
            format="%Y-%m-%d",
            attrs={"type": "date"}
        )
    )

    genero = forms.ChoiceField(
        label="Género",
        choices=GENERO_CHOICES
    )

    # =========================
    # DATOS DEL APODERADO
    # =========================
    rut_apoderado = forms.CharField(
        label="RUT del apoderado",
        max_length=12,
        validators=[validar_rut_chileno],
        widget=forms.TextInput(attrs={
            "placeholder": "Ej: 11.111.111-1"
        })
    )

    nombre_apoderado = forms.CharField(
        label="Nombre del apoderado",
        max_length=100,
        widget=forms.TextInput(attrs={
            "placeholder": "Ingrese el nombre del apoderado"
        })
    )

    apellido_apoderado = forms.CharField(
        label="Apellido del apoderado",
        max_length=100,
        widget=forms.TextInput(attrs={
            "placeholder": "Ingrese el apellido del apoderado"
        })
    )

    direccion = forms.CharField(
        label="Dirección",
        max_length=255,
        required=False,
        widget=forms.TextInput(attrs={
            "placeholder": "Ingrese la dirección"
        })
    )

    telefono = forms.CharField(
        label="Teléfono",
        max_length=20,
        required=False,
        widget=forms.TextInput(attrs={
            "placeholder": "Ej: +56 9 1234 5678"
        })
    )

    email_apoderado = forms.EmailField(
        label="Correo electrónico",
        max_length=254,
        widget=forms.EmailInput(attrs={
            "placeholder": "correo@ejemplo.com"
        })
    )

    parentesco = forms.ChoiceField(
        label="Parentesco",
        choices=PARENTESCO_CHOICES
    )

    is_principal = forms.BooleanField(
        label="Marcar como apoderado principal",
        required=False,
        initial=True
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.update({
                    "class": "form-check-input"
                })
            else:
                field.widget.attrs.update({
                    "class": "form-control"
                })

    def clean(self):
        cleaned_data = super().clean()

        rut_alumno = cleaned_data.get("rut_alumno", "").strip()
        rut_apoderado = cleaned_data.get("rut_apoderado", "").strip()
        email_apoderado = cleaned_data.get("email_apoderado", "").strip().lower()

        username_alumno = normalizar_rut_para_username(rut_alumno)
        username_apoderado = normalizar_rut_para_username(rut_apoderado)

        cleaned_data["username_alumno"] = username_alumno
        cleaned_data["username_apoderado"] = username_apoderado
        cleaned_data["email_apoderado"] = email_apoderado

        if username_alumno and username_apoderado and username_alumno == username_apoderado:
            self.add_error(
                "rut_alumno",
                "El RUT del alumno no puede ser igual al RUT del apoderado."
            )
            self.add_error(
                "rut_apoderado",
                "El RUT del apoderado no puede ser igual al RUT del alumno."
            )

        if username_alumno and (
            Usuario.objects.filter(rut__iexact=rut_alumno).exists()
            or username_ocupado(username_alumno)
        ):
            self.add_error(
                "rut_alumno",
                "Ya existe un usuario registrado con este RUT de alumno."
            )

        if username_apoderado and (
            Usuario.objects.filter(rut__iexact=rut_apoderado).exists()
            or username_ocupado(username_apoderado)
        ):
            self.add_error(
                "rut_apoderado",
                "Ya existe un usuario registrado con este RUT de apoderado."
            )

        if email_apoderado and Usuario.objects.filter(email__iexact=email_apoderado).exists():
            self.add_error(
                "email_apoderado",
                "Ya existe un usuario registrado con este correo electrónico."
            )

        if email_apoderado and Apoderado.objects.filter(email__iexact=email_apoderado).exists():
            self.add_error(
                "email_apoderado",
                "Ya existe un apoderado registrado con este correo electrónico."
            )

        if username_alumno and SolicitudPostulacion.objects.filter(
            rut_alumno_normalizado=username_alumno,
            estado="PENDIENTE"
        ).exists():
            self.add_error(
                "rut_alumno",
                "Ya existe una postulación pendiente para este alumno."
            )

        return cleaned_data


class PostulacionAlumnoForm(BaseAlumnoApoderadoForm):
    """
    Formulario público.
    No crea usuarios.
    Solo guarda una SolicitudPostulacion.
    """

    ciclo_postulacion = forms.ChoiceField(
        label="Ciclo al que postula",
        choices=[
            ("", "Seleccione ciclo"),
            (Curso.CICLO_KINDER, "Kinder"),
            (Curso.CICLO_BASICA, "Enseñanza Básica"),
            (Curso.CICLO_MEDIA, "Enseñanza Media"),
        ],
        required=True,
        widget=forms.Select(attrs={
            "id": "id_ciclo_postulacion",
            "class": "form-control"
        })
    )

    nivel_postulacion = forms.ChoiceField(
        label="Nivel al que postula",
        choices=[
            ("", "Seleccione nivel"),
            ("1", "1"),
            ("2", "2"),
            ("3", "3"),
            ("4", "4"),
            ("5", "5"),
            ("6", "6"),
            ("7", "7"),
            ("8", "8"),
        ],
        required=True,
        widget=forms.Select(attrs={
            "id": "id_nivel_postulacion",
            "class": "form-control"
        })
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.order_fields([
            "rut_alumno",
            "nombre_alumno",
            "apellido_alumno",
            "fecha_nacimiento",
            "genero",
            "ciclo_postulacion",
            "nivel_postulacion",

            "rut_apoderado",
            "nombre_apoderado",
            "apellido_apoderado",
            "direccion",
            "telefono",
            "email_apoderado",
            "parentesco",
            "is_principal",
        ])

    def clean(self):
        cleaned_data = super().clean()

        ciclo = cleaned_data.get("ciclo_postulacion")
        nivel = cleaned_data.get("nivel_postulacion")

        if not ciclo or not nivel:
            return cleaned_data

        ciclo = Curso.normalizar_ciclo(ciclo)

        try:
            nivel = int(nivel)
        except (TypeError, ValueError):
            self.add_error("nivel_postulacion", "Ingresa un nivel válido.")
            return cleaned_data

        error_nivel = Curso.validar_nivel_por_ciclo(ciclo, nivel)

        if error_nivel:
            self.add_error("nivel_postulacion", error_nivel)

        cleaned_data["ciclo_postulacion"] = ciclo
        cleaned_data["nivel_postulacion"] = nivel

        return cleaned_data

class RegistroAlumnoApoderadoForm(BaseAlumnoApoderadoForm):
    """
    Formulario interno del administrador.
    Sí crea usuarios y perfiles.
    """
    pass
