from django.db.utils import OperationalError, ProgrammingError

from .models import Curso, Docente


def docente_jefatura(request):
    user = getattr(request, "user", None)
    tiene_jefatura = False

    if user and user.is_authenticated and getattr(user, "tipo_usuario", None) == "DOCENTE":
        docente = Docente.objects.filter(usuario=user).first()
        try:
            tiene_jefatura = bool(docente and Curso.objects.filter(profesor_jefe=docente).exists())
        except (OperationalError, ProgrammingError):
            tiene_jefatura = False

    return {"docente_tiene_jefatura": tiene_jefatura}
