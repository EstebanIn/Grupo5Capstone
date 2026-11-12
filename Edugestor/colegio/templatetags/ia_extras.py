import markdown as md
import bleach
from django import template
from django.utils.html import escape
from django.utils.safestring import mark_safe

register = template.Library()


@register.filter
def markdown_seguro(texto):
    """Markdown generado por la IA a HTML. Se escapa antes: ningún HTML del modelo llega a la página."""
    html = md.markdown(escape(texto or ""), extensions=["tables", "sane_lists"])
    return mark_safe(bleach.clean(html, tags=['p', 'br', 'strong', 'em', 'h1', 'h2', 'h3', 'h4',
        'ul', 'ol', 'li', 'blockquote', 'pre', 'code', 'hr', 'table', 'thead', 'tbody', 'tr', 'th', 'td', 'a'],
        attributes={'a': ['href', 'title']}, protocols=['https', 'http'], strip=True))


@register.filter
def letra(indice):
    return "ABCDEFGH"[int(indice)] if 0 <= int(indice) < 8 else str(indice)


@register.filter
def index(lista, posicion):
    try:
        return lista[int(posicion)]
    except (IndexError, TypeError, ValueError):
        return ""
