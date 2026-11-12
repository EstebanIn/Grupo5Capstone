from celery import shared_task
from .ia.trabajos import ejecutar, limpiar


@shared_task(ignore_result=True)
def ejecutar_trabajo(pk):
    # Único argumento en Redis: UUID. Nunca claves, sesión, prompts ni adjuntos.
    ejecutar(pk)


@shared_task(ignore_result=True)
def limpiar_trabajos():
    limpiar()
