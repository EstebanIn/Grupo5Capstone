import django.db.models.deletion
from django.db import migrations, models
from pgvector.django import VectorField


def catalogo(apps, schema_editor):
    apps.get_model('colegio', 'FuenteBiblioteca').objects.get_or_create(
        slug='mineduc-matematica-4-basico', defaults={
            'titulo': 'Programa de Estudio Matemática · 4° básico',
            'ficha_url': 'https://www.curriculumnacional.cl/recursos/programa-estudio-matematica-4-basico',
            'descarga_url': 'https://www.curriculumnacional.cl/614/articles-18979_programa.pdf',
            'asignatura': 'Matemática', 'ciclo': 'BASICA', 'nivel': 4,
            'licencia': 'MINEDUC. Consultar condiciones de reutilización en la ficha y el documento original.',
            'version': 'Programa de estudio (edición del PDF oficial)',
            'aprobada': True, 'automatica': True})


class Migration(migrations.Migration):
    dependencies = [('colegio', '0023_registroia_diagnostico_trabajoia')]
    operations = [
        migrations.CreateModel(name='FuenteBiblioteca', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('slug', models.SlugField(unique=True)),
            ('titulo', models.CharField(max_length=250)),
            ('ficha_url', models.URLField(max_length=1000)),
            ('descarga_url', models.URLField(max_length=1000)),
            ('asignatura', models.CharField(max_length=120)),
            ('ciclo', models.CharField(max_length=20)),
            ('nivel', models.PositiveSmallIntegerField()),
            ('licencia', models.CharField(blank=True, max_length=250)),
            ('version', models.CharField(blank=True, max_length=80)),
            ('aprobada', models.BooleanField(default=False)),
            ('automatica', models.BooleanField(default=False)),
            ('estado', models.CharField(default='pendiente', max_length=20)),
            ('mensaje', models.CharField(blank=True, max_length=400)),
            ('comprobada', models.DateTimeField(blank=True, null=True)),
            ('proxima_revision', models.DateTimeField(blank=True, null=True)),
            ('bloqueo', models.UUIDField(blank=True, null=True)),
            ('bloqueo_hasta', models.DateTimeField(blank=True, null=True)),
        ], options={'ordering': ['asignatura', 'ciclo', 'nivel', 'titulo']}),
        migrations.AddField(model_name='documentocurricular', name='fuente_biblioteca',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                    related_name='documentos', to='colegio.fuentebiblioteca')),
        migrations.AlterField(model_name='fragmentocurricular', name='embedding', field=VectorField(dimensions=768, null=True, blank=True)),
        migrations.AddField(model_name='fragmentocurricular', name='modelo_embedding_gemini', field=models.CharField(blank=True, default='', max_length=160)),
        migrations.AddField(model_name='fragmentocurricular', name='huella_texto_gemini', field=models.CharField(blank=True, default='', max_length=64)),
        migrations.RunPython(catalogo, migrations.RunPython.noop),
    ]
