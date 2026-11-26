import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("colegio", "0025_correccionprueba_puntajes"),
    ]

    operations = [
        migrations.AlterField(
            model_name="fuentebiblioteca",
            name="descarga_url",
            field=models.URLField(
                blank=True, max_length=1000,
                help_text="PDF oficial. Si se deja vacío, se busca en la ficha al indexar."),
        ),
        migrations.AddField(
            model_name="fuentebiblioteca",
            name="propuesta_por",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                    related_name="+", to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name="fuentebiblioteca",
            name="propuesta_fecha",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="fuentebiblioteca",
            name="revisada_por",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                    related_name="+", to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name="fuentebiblioteca",
            name="revisada_fecha",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="fuentebiblioteca",
            name="motivo_rechazo",
            field=models.CharField(blank=True, max_length=300),
        ),
    ]
