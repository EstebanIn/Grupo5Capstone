"""Completa vectores Qwen de ambos corpus sin borrar Gemini."""
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from colegio.ia.indice_qwen import bloqueo_indexacion, reindexar_qwen
from colegio.ia.proveedor import ErrorIA

class Command(BaseCommand):
    help = 'Completa el índice curricular y el del tutor con Qwen; admite reanudar.'

    def handle(self,*args,**options):
        if connection.vendor != 'postgresql':
            raise CommandError('Se requiere PostgreSQL/pgvector.')
        try:
            with bloqueo_indexacion():
                estado = reindexar_qwen(self.stdout.write)
        except ErrorIA as error:
            raise CommandError(str(error)) from None
        if not estado['completo']:
            raise CommandError('La cobertura Qwen sigue incompleta.')
        self.stdout.write(self.style.SUCCESS('Índice Qwen completo. Los vectores Gemini se conservaron.'))
