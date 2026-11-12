from django import template
from colegio.ia.visuales import bloques
from colegio.ia.proveedor import ErrorIA
register=template.Library()


@register.inclusion_tag('colegio/ia/_material_visual.html')
def material_visual(texto, recursos=None, ubicacion='contenido'):
    try:return {'bloques':bloques(texto,recursos or [],ubicacion)}
    except ErrorIA:return {'bloques':[{'texto':texto}], 'error_visual':True}
