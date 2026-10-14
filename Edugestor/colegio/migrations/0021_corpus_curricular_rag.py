from django.db import migrations, models
import django.db.models.deletion
from pgvector.django import HnswIndex, VectorField


def crear_extension_vector(apps, schema_editor):
    """Solo PostgreSQL necesita la extensión; SQLite conserva la app base operativa."""
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("CREATE EXTENSION IF NOT EXISTS vector")


def crear_indice_hnsw(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(
            "CREATE INDEX fragmento_curricular_hnsw "
            "ON colegio_fragmentocurricular USING hnsw (embedding vector_cosine_ops) "
            "WITH (m = 16, ef_construction = 64)"
        )


def eliminar_indice_hnsw(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("DROP INDEX IF EXISTS fragmento_curricular_hnsw")


class Migration(migrations.Migration):
    dependencies = [
        ("colegio", "0020_correccion_prueba"),
    ]

    operations = [
        migrations.RunPython(crear_extension_vector, migrations.RunPython.noop),
        migrations.CreateModel(
            name="DocumentoCurricular",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("titulo", models.CharField(max_length=250)),
                ("fuente_url", models.URLField(blank=True, max_length=1000)),
                ("version", models.CharField(blank=True, max_length=80)),
                ("asignatura", models.CharField(db_index=True, max_length=120)),
                ("ciclo", models.CharField(blank=True, max_length=20)),
                ("nivel", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("sha256", models.CharField(max_length=64, unique=True)),
                ("activo", models.BooleanField(db_index=True, default=True)),
                ("fecha_indexacion", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ["asignatura", "ciclo", "nivel", "titulo"]},
        ),
        migrations.CreateModel(
            name="FragmentoCurricular",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("numero", models.PositiveIntegerField()),
                ("pagina", models.PositiveIntegerField(blank=True, null=True)),
                ("texto", models.TextField()),
                ("embedding", VectorField(dimensions=768)),
                ("documento", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="fragmentos",
                    to="colegio.documentocurricular",
                )),
            ],
            options={
                "ordering": ["documento_id", "numero"],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("documento", "numero"),
                        name="uq_fragmento_curricular_numero",
                    ),
                ],
            },
        ),
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(crear_indice_hnsw, eliminar_indice_hnsw),
            ],
            state_operations=[
                migrations.AddIndex(
                    model_name="fragmentocurricular",
                    index=HnswIndex(
                        name="fragmento_curricular_hnsw",
                        fields=["embedding"],
                        m=16,
                        ef_construction=64,
                        opclasses=["vector_cosine_ops"],
                    ),
                ),
            ],
        ),
    ]
