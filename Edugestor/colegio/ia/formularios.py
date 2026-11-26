from django import forms

from .asistentes import TIPOS_MATERIAL
from .dominio import cargas_docente


class CargaChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, carga):
        return f"{carga.curso} · {carga.asignatura.nombre_asignatura}"


PERSONALIZADO = ""


class FormularioBaseDocente(forms.Form):
    carga = CargaChoiceField(queryset=None, label="Curso y asignatura", empty_label="Selecciona…")
    oa = forms.ChoiceField(
        label="OA oficial del programa", required=False,
        help_text="Elige el OA de tu curso: su texto e indicadores oficiales se entregan a la IA. "
                  "Si tu curso no aparece, usa un objetivo personalizado.",
    )
    objetivo = forms.CharField(
        label="Objetivo de Aprendizaje (OA)", required=False, max_length=600,
        widget=forms.Textarea(attrs={"rows": 2, "placeholder": "Ej: comparar fracciones con material concreto y pictórico"}),
        help_text="Con un OA oficial, precisa aquí el foco (opcional). Sin OA oficial, describe tu objetivo: "
                  "quedará marcado como personalizado, no como OA oficial.",
    )

    def __init__(self, *args, docente, **kwargs):
        super().__init__(*args, **kwargs)
        from .curriculo import catalogo_de_carga
        cargas = cargas_docente(docente)
        self.fields["carga"].queryset = cargas
        grupos, vistos = [], set()
        for carga in cargas:
            datos = catalogo_de_carga(carga)
            if not datos or id(datos) in vistos:
                continue
            vistos.add(id(datos))
            grupos.append((f"{datos['asignatura']} · {datos['nivel']}° básico", [
                (oa["codigo"], f"{oa['codigo']} · {oa['texto'][:90]}{'…' if len(oa['texto']) > 90 else ''}")
                for oa in datos["objetivos"]]))
        self.fields["oa"].choices = [(PERSONALIZADO, "Objetivo personalizado (lo escribo abajo)")] + grupos
        if not grupos:
            self.fields["oa"].widget = forms.HiddenInput()
        # Al recuperar un trabajo, el campo de texto vuelve a mostrar solo el foco escrito.
        if self.initial.get("oa"):
            self.initial["objetivo"] = self.initial.get("foco", "")

    def clean(self):
        datos = super().clean()
        codigo = datos.get("oa") or PERSONALIZADO
        datos["oa"] = codigo
        if codigo and datos.get("carga"):
            from .curriculo import objetivo, texto_objetivo
            oa = objetivo(codigo, carga=datos["carga"])
            if oa is None:
                self.add_error("oa", "Ese OA no corresponde al curso y asignatura elegidos.")
                return datos
            datos["foco"] = datos.get("objetivo", "")
            datos["objetivo"] = texto_objetivo(oa, datos["foco"])
        return datos


class FormularioPrueba(FormularioBaseDocente):
    tema = forms.CharField(label="Tema o contenido", max_length=200,
                           widget=forms.TextInput(attrs={"placeholder": "Ej: fracciones equivalentes"}))
    cantidad = forms.IntegerField(label="Preguntas de selección múltiple", min_value=3, max_value=20, initial=8)
    cantidad_desarrollo = forms.IntegerField(
        label="Preguntas de desarrollo", min_value=0, max_value=5, initial=1, required=False,
        help_text="El estudiante escribe su desarrollo, la fórmula o concepto usado y el resultado. "
                  "En Matemática y Ciencias se pide el cálculo; en otras asignaturas, la justificación y la conclusión.",
    )
    dificultad = forms.ChoiceField(label="Dificultad", initial="media", choices=[
        ("baja", "Baja"), ("media", "Media"), ("alta", "Alta"), ("mixta", "Mixta (de menor a mayor)"),
    ])

    def clean_cantidad_desarrollo(self):
        return self.cleaned_data.get("cantidad_desarrollo") or 0


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
    contexto_curricular = forms.ChoiceField(
        label="Fuentes del material", required=False, initial="curricular",
        choices=[
            ("curricular", "Usar documentos curriculares indexados"),
            ("personalizado", "Objetivo personalizado (sin fuentes)"),
        ],
        help_text="El modo personalizado permite generar el borrador sin un índice curricular; no acredita alineación con un OA oficial.",
    )
    tema = forms.CharField(label="Tema", max_length=200,
                           widget=forms.TextInput(attrs={"placeholder": "Ej: los estados del agua"}))
    tipo = forms.ChoiceField(label="Tipo de material", choices=list(TIPOS_MATERIAL.items()))

    def __init__(self, *args, docente, **kwargs):
        super().__init__(*args, docente=docente, **kwargs)
        self.fields['objetivo'].label = 'Objetivo de aprendizaje del material'
        self.fields['objetivo'].help_text = 'Puede indicar un OA verificado o describir un objetivo personalizado.'
        if not self.is_bound and 'contexto_curricular' not in self.initial:
            from django.db.models import Q
            from colegio.models import FragmentoCurricular
            cargas = self.fields['carga'].queryset
            seleccion = self.initial.get('carga')
            if seleccion:
                cargas = cargas.filter(pk=getattr(seleccion, 'pk', seleccion))
            hay_fuentes = any(FragmentoCurricular.objects.filter(
                documento__activo=True,
                documento__asignatura__iexact=carga.asignatura.nombre_asignatura,
                documento__ciclo__in=(carga.curso.ciclo, ''),
            ).filter(Q(documento__nivel=carga.curso.nivel) | Q(documento__nivel__isnull=True)).exists()
                for carga in cargas)
            if not hay_fuentes:
                self.initial['contexto_curricular'] = 'personalizado'
                self.fields['contexto_curricular'].help_text = (
                    'No hay fuentes indexadas para los cursos consultados. Puede generar un borrador '
                    'con objetivo personalizado o seleccionar RAG después de indexar las fuentes. '
                    'El modo personalizado no acredita alineación con un OA oficial.')

    def clean_contexto_curricular(self):
        # Los formularios antiguos y trabajos recuperados conservan su modo RAG.
        return self.cleaned_data.get('contexto_curricular') or 'curricular'


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
