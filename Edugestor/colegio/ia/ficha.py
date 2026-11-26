"""
Ficha visual del material de estudio (formato infografía de una página).

La IA entrega solo datos: textos breves y el nombre de un ícono del catálogo.
El servidor valida, recorta y dibuja la ficha con SVG propios; nunca se
renderiza HTML, SVG ni URL entregados por el modelo.
"""
import re

ICONOS = {
    "libro": "Libro", "lapiz": "Lápiz", "idea": "Ampolleta", "lupa": "Lupa",
    "resumen": "Hoja con lupa", "fichas": "Fichas", "audio": "Audio", "mapa": "Mapa conceptual",
    "conversar": "Conversación", "ejercicio": "Ejercicio", "calculadora": "Calculadora",
    "regla": "Regla", "reloj": "Reloj", "meta": "Meta", "pregunta": "Pregunta",
    "estrella": "Estrella", "planta": "Planta", "mundo": "Mundo", "grafico": "Gráfico", "check": "Logrado",
}
ICONO_POR_DEFECTO = "idea"
MIN_TARJETAS, MAX_TARJETAS = 4, 8
LIMITES = {"titulo": 60, "subtitulo": 60, "pregunta": 60, "respuesta": 160, "recuerda": 120,
           "tarjeta_titulo": 40, "tarjeta_texto": 110}


def _texto(valor, limite):
    """Una línea de texto plano, sin espacios repetidos, recortada en una palabra completa."""
    texto = re.sub(r"\s+", " ", str(valor or "")).strip()
    if len(texto) <= limite:
        return texto
    corte = texto[:limite - 1].rsplit(" ", 1)[0].rstrip(",;:")
    return f"{corte}…"


def normalizar_icono(valor):
    clave = str(valor or "").strip().lower()
    clave = clave.translate(str.maketrans("áéíóúñ", "aeioun"))
    return clave if clave in ICONOS else ICONO_POR_DEFECTO


def validar_ficha(datos):
    """Retorna la ficha normalizada, o None si no hay suficiente contenido usable."""
    if not isinstance(datos, dict):
        return None
    idea = datos.get("idea") if isinstance(datos.get("idea"), dict) else {}
    tarjetas = []
    for tarjeta in datos.get("tarjetas") or []:
        if not isinstance(tarjeta, dict):
            continue
        titulo = _texto(tarjeta.get("titulo"), LIMITES["tarjeta_titulo"])
        if not titulo:
            continue
        tarjetas.append({"titulo": titulo, "texto": _texto(tarjeta.get("texto"), LIMITES["tarjeta_texto"]),
                         "icono": normalizar_icono(tarjeta.get("icono"))})
    titulo = _texto(datos.get("titulo"), LIMITES["titulo"])
    if not titulo or len(tarjetas) < MIN_TARJETAS:
        return None
    return {
        "titulo": titulo,
        "subtitulo": _texto(datos.get("subtitulo"), LIMITES["subtitulo"]),
        "idea": {"pregunta": _texto(idea.get("pregunta"), LIMITES["pregunta"]),
                 "respuesta": _texto(idea.get("respuesta"), LIMITES["respuesta"])},
        "tarjetas": tarjetas[:MAX_TARJETAS],
        "recuerda": _texto(datos.get("recuerda"), LIMITES["recuerda"]),
    }


def ficha_vacia(titulo=""):
    """Plantilla editable para que el docente arme la ficha a mano."""
    return {"titulo": _texto(titulo, LIMITES["titulo"]), "subtitulo": "Guía para el estudio",
            "idea": {"pregunta": "¿Qué es?", "respuesta": ""},
            "tarjetas": [{"titulo": "", "texto": "", "icono": icono}
                         for icono in ("libro", "resumen", "mapa", "ejercicio")],
            "recuerda": ""}


def ficha_desde_post(post):
    """
    Ficha enviada desde el editor. Retorna (ficha, presente):
    presente=False si el formulario no incluye la sección de ficha.
    """
    if post.get("ficha_presente") != "1":
        return None, False
    if post.get("ficha_quitar"):
        return None, True
    indices = sorted({int(m[1]) for k in post if (m := re.fullmatch(r"ficha_t(\d{1,2})_titulo", k))})
    datos = {
        "titulo": post.get("ficha_titulo", ""), "subtitulo": post.get("ficha_subtitulo", ""),
        "idea": {"pregunta": post.get("ficha_pregunta", ""), "respuesta": post.get("ficha_respuesta", "")},
        "recuerda": post.get("ficha_recuerda", ""),
        "tarjetas": [{"titulo": post.get(f"ficha_t{i}_titulo", ""), "texto": post.get(f"ficha_t{i}_texto", ""),
                      "icono": post.get(f"ficha_t{i}_icono", "")}
                     for i in indices if not post.get(f"ficha_t{i}_eliminar")],
    }
    return datos, True


def textos_ficha(ficha):
    if not isinstance(ficha, dict):
        return []
    idea = ficha.get("idea") or {}
    textos = [ficha.get("titulo", ""), ficha.get("subtitulo", ""), idea.get("pregunta", ""),
              idea.get("respuesta", ""), ficha.get("recuerda", "")]
    for tarjeta in ficha.get("tarjetas", []):
        textos += [tarjeta.get("titulo", ""), tarjeta.get("texto", ""), tarjeta.get("icono", "")]
    return textos
