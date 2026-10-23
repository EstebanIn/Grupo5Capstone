"""Completa vectores Qwen de ambos corpus sin borrar Gemini."""
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from colegio.ia.indice_qwen import reindexar_qwen
from colegio.ia.proveedor import ErrorIA

class Command(BaseCommand):
    help = 'Completa el índice curricular y el del tutor con Qwen; admite reanudar.'

    def handle(self,*args,**options):
        if connection.vendor != 'postgresql':
            raise CommandError('Se requiere PostgreSQL/pgvector.')
        with connection.cursor() as cursor:
            cursor.execute('SELECT pg_try_advisory_lock(78331357)')
            if not cursor.fetchone()[0]:
                raise CommandError('Ya hay una reindexación Qwen en ejecución.')
        try:
            estado = reindexar_qwen(self.stdout.write)
            if not estado['completo']:
                raise CommandError('La cobertura Qwen sigue incompleta.')
            self.stdout.write(self.style.SUCCESS('Índice Qwen completo. Los vectores Gemini se conservaron.'))
        except ErrorIA as error:
            raise CommandError(str(error)) from None
        finally:
            with connection.cursor() as cursor:
                cursor.execute('SELECT pg_advisory_unlock(78331357)')
