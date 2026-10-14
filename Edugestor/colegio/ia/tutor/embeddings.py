import time

from django.conf import settings
from google import genai
from google.genai import types, errors


# ============================================================
# CONFIGURACIÓN
# ============================================================

MODELO_EMBEDDING = "gemini-embedding-001"
DIMENSION_EMBEDDING = 768
MAX_INTENTOS = 6

_cliente = None


# ============================================================
# CLIENTE GEMINI
# ============================================================

def obtener_cliente():
    """
    Crea el cliente Gemini una sola vez
    y lo reutiliza durante toda la ejecución.
    """

    global _cliente

    if _cliente is not None:
        return _cliente

    api_key = getattr(
        settings,
        "GEMINI_API_KEY",
        ""
    )

    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY no está configurada."
        )

    _cliente = genai.Client(
        api_key=api_key
    )

    return _cliente


# ============================================================
# VALIDACIÓN DE TEXTO
# ============================================================

def _validar_texto(texto):
    """
    Limpia y valida un texto antes de enviarlo a Gemini.
    """

    if texto is None:
        raise ValueError(
            "No se puede generar embedding de un texto vacío."
        )

    texto = str(texto).strip()

    if not texto:
        raise ValueError(
            "No se puede generar embedding de un texto vacío."
        )

    return texto


# ============================================================
# ESPERA ENTRE REINTENTOS
# ============================================================

def _esperar_reintento(
    intento,
    codigo,
    max_intentos
):
    """
    Espera progresiva para rate limits y errores temporales.
    """

    if codigo == 429:
        espera = min(
            10 * (2 ** (intento - 1)),
            90
        )
    else:
        espera = min(
            5 * (2 ** (intento - 1)),
            60
        )

    print(
        f"Gemini respondió HTTP {codigo}. "
        f"Intento {intento}/{max_intentos}. "
        f"Reintentando en {espera}s..."
    )

    time.sleep(espera)


# ============================================================
# GENERAR EMBEDDINGS EN BATCH
# ============================================================

def generar_embeddings(
    textos,
    max_intentos=MAX_INTENTOS
):
    """
    Genera embeddings para varios textos
    utilizando una sola solicitud a Gemini.
    """

    if not textos:
        return []

    textos = [
        _validar_texto(texto)
        for texto in textos
    ]

    cliente = obtener_cliente()

    ultimo_error = None

    for intento in range(
        1,
        max_intentos + 1
    ):

        try:
            respuesta = cliente.models.embed_content(
                model=MODELO_EMBEDDING,
                contents=textos,
                config=types.EmbedContentConfig(
                    output_dimensionality=DIMENSION_EMBEDDING
                ),
            )

            if not respuesta.embeddings:
                raise RuntimeError(
                    "Gemini no devolvió embeddings."
                )

            if len(respuesta.embeddings) != len(textos):
                raise RuntimeError(
                    "La cantidad de embeddings recibidos "
                    "no coincide con los textos enviados."
                )

            vectores = []

            for embedding in respuesta.embeddings:
                vector = embedding.values

                if len(vector) != DIMENSION_EMBEDDING:
                    raise RuntimeError(
                        "Dimensión inesperada. "
                        f"Esperada: {DIMENSION_EMBEDDING}. "
                        f"Recibida: {len(vector)}."
                    )

                vectores.append(vector)

            return vectores

        # ====================================================
        # ERRORES TEMPORALES SERVIDOR
        # ====================================================

        except errors.ServerError as error:
            ultimo_error = error

            codigo = getattr(
                error,
                "code",
                None
            )

            if codigo in (
                500,
                502,
                503,
                504
            ):
                if intento >= max_intentos:
                    break

                _esperar_reintento(
                    intento,
                    codigo,
                    max_intentos
                )

                continue

            raise

        # ====================================================
        # ERRORES CLIENTE
        # ====================================================

        except errors.ClientError as error:
            ultimo_error = error

            codigo = getattr(
                error,
                "code",
                None
            )

            if codigo == 429:
                print(
                    "\n=== GEMINI RATE LIMIT ==="
                )

                print(error)

                print(
                    "=========================\n"
                )

                if intento >= max_intentos:
                    break

                _esperar_reintento(
                    intento,
                    codigo,
                    max_intentos
                )

                continue

            if codigo == 401:
                raise RuntimeError(
                    "Gemini rechazó la autenticación. "
                    "Revisa GEMINI_API_KEY."
                ) from error

            if codigo == 403:
                raise RuntimeError(
                    "El proyecto Gemini no tiene permisos "
                    "para embeddings."
                ) from error

            if codigo == 404:
                raise RuntimeError(
                    "Modelo de embeddings no encontrado: "
                    f"{MODELO_EMBEDDING}"
                ) from error

            raise

        # ====================================================
        # ERRORES RED
        # ====================================================

        except (
            ConnectionError,
            TimeoutError
        ) as error:
            ultimo_error = error

            if intento >= max_intentos:
                break

            espera = min(
                5 * (2 ** (intento - 1)),
                60
            )

            print(
                "Error de conexión con Gemini. "
                f"Intento {intento}/{max_intentos}. "
                f"Reintentando en {espera}s..."
            )

            time.sleep(espera)

    raise RuntimeError(
        "No fue posible generar los embeddings "
        f"después de {max_intentos} intentos."
    ) from ultimo_error


# ============================================================
# GENERAR UN SOLO EMBEDDING
# ============================================================

def generar_embedding(
    texto,
    max_intentos=MAX_INTENTOS
):
    """
    Genera el embedding de un único texto.

    Se utiliza para preguntas del alumno
    y búsquedas individuales.
    """

    vectores = generar_embeddings(
        [texto],
        max_intentos=max_intentos
    )

    return vectores[0]