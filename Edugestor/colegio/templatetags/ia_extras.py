import markdown as md
import bleach
import re
from django import template
from django.utils.html import escape
from django.utils.safestring import mark_safe

register = template.Library()


@register.filter
def markdown_seguro(texto):
    """Markdown generado por la IA a HTML. Se escapa antes: ningún HTML del modelo llega a la página."""
    lineas=[]
    en_codigo=False
    lista=re.compile(r'^(?:\d{1,4}[.)]|[-+*])\s+')
    separador=re.compile(r'^\s{0,3}(?:_\s*){3,}$')
    guiones_bajos=re.compile(r'_{2,}')
    for linea in str(texto or '').replace('\r\n','\n').split('\n'):
        if linea.lstrip().startswith(('```','~~~')):
            en_codigo=not en_codigo
        if (not en_codigo and lista.match(linea) and lineas and lineas[-1].strip()
                and not lista.match(lineas[-1])):
            lineas.append('')
        if not en_codigo and not separador.match(linea):
            # "___" es un espacio para completar, no énfasis: se escapa para que se vea.
            linea = guiones_bajos.sub(lambda m: '\\_' * len(m.group()), linea)
        lineas.append(linea)
    # El texto se escapa entero; solo se devuelve su sentido al ">" de las citas Markdown
    # (por ejemplo, el recuadro "> **Recuerda:**"), que bleach permite como <blockquote>.
    seguro = re.sub(r'(?m)^( {0,3})&gt;', r'\1>', str(escape('\n'.join(lineas))))
    html = md.markdown(seguro, extensions=["tables", "sane_lists"])
    return mark_safe(bleach.clean(html, tags=['p', 'br', 'strong', 'em', 'h1', 'h2', 'h3', 'h4',
        'ul', 'ol', 'li', 'blockquote', 'pre', 'code', 'hr', 'table', 'thead', 'tbody', 'tr', 'th', 'td', 'a'],
        attributes={'a': ['href', 'title'], 'ol': ['start']}, protocols=['https', 'http'], strip=True))


@register.filter
def falta_punto(texto):
    """El punto que le falta a una frase para cerrarla ('' si ya termina en signo final)."""
    texto = str(texto if texto is not None else '').rstrip()
    return '' if not texto or texto[-1] in '.!?…:;)' else '.'


@register.filter
def con_punto(texto):
    """Cierra una frase con punto, sin duplicarlo si ya termina en signo final."""
    texto = str(texto if texto is not None else '').rstrip()
    return texto + falta_punto(texto)


@register.filter
def letra(indice):
    return "ABCDEFGH"[int(indice)] if 0 <= int(indice) < 8 else str(indice)


@register.filter
def index(lista, posicion):
    try:
        return lista[int(posicion)]
    except (IndexError, TypeError, ValueError):
        return ""


@register.filter
def valor(diccionario, clave):
    """Acceso a un diccionario por clave variable: {{ dic|valor:clave }}."""
    if isinstance(diccionario, dict):
        resultado = diccionario.get(clave)
        return "" if resultado is None else resultado
    return ""
