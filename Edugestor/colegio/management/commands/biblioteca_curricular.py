from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from colegio.ia.proveedor import ErrorIA


class Command(BaseCommand):
    help = 'Sincroniza o traslada la biblioteca pública. Importar exige un paquete de confianza.'

    def add_arguments(self, parser):
        parser.add_argument('accion', choices=['sincronizar','exportar','importar','vectores'])
        parser.add_argument('--archivo')
        parser.add_argument('--fuente', default='mineduc-matematica-4-basico')
        parser.add_argument('--proveedor', choices=['gemini','qwen'])
        parser.add_argument('--maximo', type=int, default=50)

    def handle(self, *args, **options):
        from colegio.ia.biblioteca_catalogo import preparar_catalogo
        from colegio.ia import biblioteca, biblioteca_paquetes
        from colegio.models import FuenteBiblioteca
        preparar_catalogo()
        try:
            accion = options['accion']
            if accion=='sincronizar':
                f = FuenteBiblioteca.objects.get(slug=options['fuente'], aprobada=True)
                resultado = biblioteca.sincronizar(f.pk, informar=self.stdout.write)['mensaje']
            elif accion=='vectores':
                cantidad = biblioteca.indexar_vectores(options['proveedor'], maximo=options['maximo'], informar=self.stdout.write)
                resultado = f'{cantidad} fragmentos procesados. Repite para continuar los pendientes.'
            else:
                if not options['archivo']:
                    raise CommandError('Esta operación requiere --archivo.')
                ruta = Path(options['archivo'])
                if accion=='exportar':
                    if ruta.exists():
                        raise CommandError('El archivo de destino ya existe. Usa otro nombre.')
                    ruta.write_bytes(biblioteca_paquetes.exportar()); resultado = 'Biblioteca pública exportada sin credenciales.'
                else:
                    if ruta.stat().st_size>biblioteca_paquetes.MAX_PAQUETE:
                        raise CommandError('El paquete excede 100 MB.')
                    resultado = f'{biblioteca_paquetes.importar(ruta.read_bytes())} documentos importados.'
        except (ErrorIA, FuenteBiblioteca.DoesNotExist) as error:
            raise CommandError(str(error)) from None
        self.stdout.write(self.style.SUCCESS(resultado))
