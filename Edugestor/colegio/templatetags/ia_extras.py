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
    for linea in str(texto or '').replace('\r\n','\n').split('\n'):
        if linea.lstrip().startswith(('```','~~~')):
            en_codigo=not en_codigo
        if (not en_codigo and lista.match(linea) and lineas and lineas[-1].strip()
                and not lista.match(lineas[-1])):
            lineas.append('')
        lineas.append(linea)
    html = md.markdown(escape('\n'.join(lineas)), extensions=["tables", "sane_lists"])
    return mark_safe(bleach.clean(html, tags=['p', 'br', 'strong', 'em', 'h1', 'h2', 'h3', 'h4',
        'ul', 'ol', 'li', 'blockquote', 'pre', 'code', 'hr', 'table', 'thead', 'tbody', 'tr', 'th', 'td', 'a'],
        attributes={'a': ['href', 'title'], 'ol': ['start']}, protocols=['https', 'http'], strip=True))


@register.filter
def letra(indice):
    return "ABCDEFGH"[int(indice)] if 0 <= int(indice) < 8 else str(indice)


@register.filter
def index(lista, posicion):
    try:
        return lista[int(posicion)]
    except (IndexError, TypeError, ValueError):
        return ""
