from django import forms

from .asistentes import TIPOS_MATERIAL
from .dominio import cargas_docente


class CargaChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, carga):
        return f"{carga.curso} · {carga.asignatura.nombre_asignatura}"


class FormularioBaseDocente(forms.Form):
    carga = CargaChoiceField(queryset=None, label="Curso y asignatura", empty_label="Selecciona…")
    objetivo = forms.CharField(
        label="Objetivo de Aprendizaje (OA)", required=False, max_length=600,
        widget=forms.Textarea(attrs={"rows": 2, "placeholder": "Ej: OA 3 — Describir y aplicar estrategias de cálculo mental para multiplicaciones…"}),
        help_text="Copia el OA de las Bases Curriculares. Mientras más preciso, mejor el resultado.",
    )

    def __init__(self, *args, docente, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["carga"].queryset = cargas_docente(docente)


class FormularioPrueba(FormularioBaseDocente):
    tema = forms.CharField(label="Tema o contenido", max_length=200,
                           widget=forms.TextInput(attrs={"placeholder": "Ej: fracciones equivalentes"}))
    cantidad = forms.IntegerField(label="Cantidad de preguntas", min_value=3, max_value=20, initial=8)
    dificultad = forms.ChoiceField(label="Dificultad", initial="media", choices=[
        ("baja", "Baja"), ("media", "Media"), ("alta", "Alta"), ("mixta", "Mixta (de menor a mayor)"),
    ])


class FormularioRubrica(FormularioBaseDocente):
    actividad = forms.CharField(
        label="Actividad a evaluar", max_length=600,
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": "Ej: disertación grupal sobre el ciclo del agua, 5 minutos, con apoyo visual"}),
    )
    criterios = forms.CharField(
        label="Criterios que quieres incluir (opcional)", required=False, max_length=600,
        widget=forms.Textarea(attrs={"rows": 2, "placeholder": "Ej: dominio del tema, uso del lenguaje, trabajo en equipo"}),
    )
    niveles = forms.TypedChoiceField(label="Niveles de desempeño", coerce=int, initial=4, choices=[
        (4, "4 niveles (Destacado · Logrado · En desarrollo · Inicial)"),
        (3, "3 niveles (Logrado · Medianamente logrado · Por lograr)"),
    ])


class FormularioMaterial(FormularioBaseDocente):
    tema = forms.CharField(label="Tema", max_length=200,
                           widget=forms.TextInput(attrs={"placeholder": "Ej: los estados del agua"}))
    tipo = forms.ChoiceField(label="Tipo de material", choices=list(TIPOS_MATERIAL.items()))


class FormularioRevision(FormularioBaseDocente):
    texto = forms.CharField(
        label="Prueba a revisar", max_length=15000,
        widget=forms.Textarea(attrs={"rows": 14, "placeholder": "Pega aquí el texto de la prueba: enunciados y alternativas."}),
    )


class FormularioTutor(forms.Form):
    mensaje = forms.CharField(
        max_length=1000, label="",
        widget=forms.Textarea(attrs={"rows": 2, "placeholder": "Escribe tu pregunta… (no escribas tu nombre ni datos personales)"}),
    )
