from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("colegio", "0024_biblioteca"),
    ]

    operations = [
        migrations.AddField(
            model_name="correccionprueba",
            name="puntaje_maximo",
            field=models.DecimalField(
                blank=True, decimal_places=1, max_digits=6, null=True,
                help_text="Suma de puntajes: 1 por selección múltiple más los criterios de desarrollo."),
        ),
        migrations.AddField(
            model_name="correccionprueba",
            name="puntaje_obtenido",
            field=models.DecimalField(blank=True, decimal_places=1, max_digits=6, null=True),
        ),
    ]
