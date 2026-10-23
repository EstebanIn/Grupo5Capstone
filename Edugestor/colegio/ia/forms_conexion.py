"""Validación de datos introducidos desde el Registro de IA."""
from urllib.parse import urlsplit
from django import forms


def validar_endpoint(url):
    try:
        parsed = urlsplit(url)
        permitido = parsed.hostname in ('dashscope-intl.aliyuncs.com', 'dashscope.aliyuncs.com') or bool(
            parsed.hostname and parsed.hostname.endswith('.maas.aliyuncs.com'))
        if (parsed.scheme != 'https' or not permitido or parsed.username or parsed.password
                or parsed.query or parsed.fragment or parsed.port not in (None, 443)
                or parsed.path.rstrip('/') != '/compatible-mode/v1'):
            raise ValueError
    except ValueError:
        raise forms.ValidationError('Usa el API Host HTTPS de Model Studio seguido de /compatible-mode/v1, sin parámetros ni credenciales.') from None
    return url.rstrip('/')


class ConexionIAForm(forms.Form):
    api_key = forms.CharField(label='Clave API', max_length=2048, strip=True,
        widget=forms.PasswordInput(render_value=False, attrs={'autocomplete': 'new-password', 'placeholder': 'Pega tu clave API', 'spellcheck': 'false'}))
    model = forms.RegexField(label='Modelo de generación', regex=r'^[a-zA-Z0-9._:-]{1,160}$', max_length=160, widget=forms.Select,
        error_messages={'invalid': 'Usa el identificador del modelo, sin espacios.'})
    base_url = forms.URLField(label='Base URL compatible con OpenAI', required=False, max_length=300,
        widget=forms.URLInput(attrs={'placeholder': 'https://dashscope-intl.aliyuncs.com/compatible-mode/v1'}))

    def __init__(self, *args, proveedor, **kwargs):
        self.proveedor = proveedor
        super().__init__(*args, **kwargs)
        # El catálogo se carga sin bloquear la página; conservar siempre el valor actual.
        modelo = self.data.get(self.add_prefix('model')) if self.is_bound else self.initial.get('model')
        self.fields['model'].widget.choices = [(modelo, modelo)] if modelo else [('', 'Selecciona un modelo')]
        if proveedor != 'qwen':
            del self.fields['base_url']
        else:
            self.fields['base_url'].required = True

    def clean_api_key(self):
        clave = self.cleaned_data['api_key']
        if any(c.isspace() or ord(c) < 33 or ord(c) > 126 for c in clave):
            raise forms.ValidationError('La clave no puede contener espacios ni saltos de línea.')
        return clave

    def clean_base_url(self):
        return validar_endpoint(self.cleaned_data['base_url'])


class ConsultaModelosForm(ConexionIAForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        del self.fields['model']
        self.fields['api_key'].required = False
