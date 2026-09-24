from django.http import Http404

from .models import Institucion
from .tenancy import activar_institucion, desactivar_institucion


class InstitucionMiddleware:
    """
    Resuelve la institución del request antes de que la vista consulte datos.

    - Usuario autenticado: su propia institución.
    - Página pública con slug_colegio en la URL (landing, postulación): la
      institución de ese slug, esté o no autenticado quien visita.

    La institución queda en request.institucion y activa para los managers
    mientras dura el request.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        institucion = user.institucion if user is not None and user.is_authenticated else None

        request.institucion = institucion
        request._tokens_institucion = [activar_institucion(institucion)]
        try:
            return self.get_response(request)
        finally:
            # Se restauran en orden inverso (LIFO), como exige ContextVar.
            for token in reversed(request._tokens_institucion):
                desactivar_institucion(token)

    def process_view(self, request, view_func, view_args, view_kwargs):
        slug = view_kwargs.get("slug_colegio")
        if not slug:
            return None

        institucion = Institucion.objects.filter(slug=slug, activa=True).first()
        if institucion is None:
            raise Http404("Institución no encontrada.")

        # Las rutas con slug son públicas (landing, postulación) y no muestran datos
        # privados: se atienden con la institución de la URL aunque quien visita
        # tenga sesión en otra.
        request.institucion = institucion
        request._tokens_institucion.append(activar_institucion(institucion))
        return None
