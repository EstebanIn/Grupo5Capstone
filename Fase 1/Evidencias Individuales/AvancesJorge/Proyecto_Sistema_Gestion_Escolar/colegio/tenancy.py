"""
Soporte multi-institución (multi-inquilino lógico).

Cada request trabaja sobre una "institución activa", guardada en una ContextVar
por InstitucionMiddleware. Los managers de los modelos institucionales filtran
automáticamente por ella, de modo que las vistas existentes quedan aisladas sin
tener que agregar el filtro a mano en cada consulta.

Sin institución activa (comandos de gestión, migraciones, superusuario de
plataforma) no se filtra.
"""

from contextlib import contextmanager
from contextvars import ContextVar

from django.contrib.auth.models import UserManager
from django.db import models

_institucion_actual = ContextVar("institucion_actual", default=None)


def obtener_institucion_actual():
    return _institucion_actual.get()


def activar_institucion(institucion):
    """Activa la institución y retorna el token para restaurar el estado anterior."""
    return _institucion_actual.set(institucion)


def desactivar_institucion(token):
    _institucion_actual.reset(token)


@contextmanager
def institucion_activa(institucion):
    token = activar_institucion(institucion)
    try:
        yield institucion
    finally:
        desactivar_institucion(token)


class InstitucionQuerySet(models.QuerySet):
    """
    Agrega el filtro por institución al crear o clonar el queryset, nunca
    modificando el original. Así, un queryset definido al importar (por ejemplo
    el de un ModelChoiceField) no queda fijado a la institución del primer
    request que lo use: cada request trabaja sobre su propio clon filtrado.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._institucion_filtrada = False

    def _clone(self):
        clon = super()._clone()
        clon._institucion_filtrada = self._institucion_filtrada
        return clon._filtrar_institucion()

    def _filtrar_institucion(self):
        institucion = obtener_institucion_actual()
        if institucion is not None and not self._institucion_filtrada:
            self._institucion_filtrada = True
            self.query.add_q(models.Q(institucion_id=institucion.pk))
        return self


class InstitucionManager(models.Manager.from_queryset(InstitucionQuerySet)):
    def get_queryset(self):
        return super().get_queryset()._filtrar_institucion()


class UsuarioManager(UserManager.from_queryset(InstitucionQuerySet)):
    def get_queryset(self):
        return super().get_queryset()._filtrar_institucion()


class InstitucionCruzadaError(ValueError):
    """Un registro intenta relacionar datos de dos instituciones distintas."""


def resolver_institucion(instancia, padres=()):
    """
    Completa instancia.institucion_id a partir de sus relaciones padre o de la
    institución activa, y verifica que ningún padre pertenezca a otra.
    """
    for nombre in padres:
        padre = getattr(instancia, nombre, None)
        if padre is None or padre.institucion_id is None:
            continue
        if instancia.institucion_id is None:
            instancia.institucion_id = padre.institucion_id
        elif padre.institucion_id != instancia.institucion_id:
            raise InstitucionCruzadaError(
                f"{instancia.__class__.__name__}.{nombre} pertenece a otra institución."
            )

    if instancia.institucion_id is None:
        actual = obtener_institucion_actual()
        if actual is not None:
            instancia.institucion_id = actual.pk
