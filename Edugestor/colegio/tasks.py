from celery import shared_task
from .ia.trabajos import ejecutar, limpiar


@shared_task(ignore_result=True)
def ejecutar_trabajo(pk):
    # Único argumento en Redis: UUID. Nunca claves, sesión, prompts ni adjuntos.
    ejecutar(pk)


@shared_task(ignore_result=True)
def limpiar_trabajos():
    limpiar()


@shared_task(ignore_result=True)
def actualizar_biblioteca():
    from django.conf import settings
    from django.db.models import Q
    from django.utils import timezone
    from .models import FuenteBiblioteca
    from .ia.biblioteca import sincronizar, limpiar_interrumpidas
    from .ia.proveedor import ErrorIA
    if not settings.BIBLIOTECA_AUTOMATICA:
        return
    limpiar_interrumpidas()
    # Un documento por ejecución; el arrendamiento evita solapamientos entre workers.
    fuente = FuenteBiblioteca.objects.filter(aprobada=True, automatica=True).filter(
        Q(proxima_revision__isnull=True) | Q(proxima_revision__lte=timezone.now())).filter(
        Q(bloqueo_hasta__isnull=True) | Q(bloqueo_hasta__lt=timezone.now())).order_by('proxima_revision', 'pk').first()
    if fuente:
        try:
            sincronizar(fuente.pk)
        except ErrorIA:
            pass  # Diagnóstico seguro y próximo intento persistidos en el catálogo.
