"""Importa un PDF oficial a fragmentos y embeddings del corpus RAG."""

import hashlib
import json
import re
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from pypdf import PdfReader

from colegio.ia.rag import DIMENSIONES_EMBEDDING, crear_embeddings
from colegio.models import DocumentoCurricular, FragmentoCurricular


class Command(BaseCommand):
    help = "Indexa un PDF curricular oficial del Mineduc para la recuperación RAG."

    def add_arguments(self, parser):
        parser.add_argument("pdf", type=Path, help="Ruta local al PDF descargado desde una fuente oficial")
        parser.add_argument("--titulo", required=True, help="Título legible del documento")
        parser.add_argument("--asignatura", required=True, help="Nombre de asignatura, por ejemplo Matemática")
        parser.add_argument("--ciclo", required=True, choices=("KINDER", "BASICA", "MEDIA"))
        parser.add_argument("--nivel", type=int, help="Nivel: Kinder=1, Básica=1-8, Media=1-4")
        parser.add_argument("--url", default="", help="URL pública de la fuente Mineduc")
        parser.add_argument("--version-documento", default="", help="Año o versión del documento")

    def handle(self, *args, **options):
        archivo = options["pdf"]
        if connection.vendor != "postgresql":
            raise CommandError("El índice vectorial requiere PostgreSQL con pgvector; inicia Docker Compose primero.")
        if not settings.GEMINI_API_KEY:
            raise CommandError("Configura GEMINI_API_KEY en Edugestor/.env antes de indexar el PDF.")
        if not archivo.is_file() or archivo.suffix.lower() != ".pdf":
            raise CommandError(f"No se encontró un archivo PDF válido: {archivo}")
        nivel = options["nivel"]
        if nivel is not None and nivel < 1:
            raise CommandError("El nivel debe ser un entero positivo.")

        contenido_pdf = archivo.read_bytes()
        checksum = hashlib.sha256(contenido_pdf).hexdigest()
        try:
            lector = PdfReader(archivo)
            fragmentos = []
            for numero_pagina, pagina in enumerate(lector.pages, start=1):
                for contenido in _fragmentar(pagina.extract_text() or ""):
                    fragmentos.append({
                        "numero": len(fragmentos) + 1,
                        "pagina": numero_pagina,
                        "contenido": contenido,
                    })
        except Exception as error:
            raise CommandError(f"No se pudo leer el PDF: {error}") from error
        if not fragmentos:
            raise CommandError("El PDF no contiene texto extraíble. Los documentos escaneados requieren OCR antes de indexarlos.")

        corpus = {
            "esquema": "edugestor-corpus-curricular-v1",
            "documento": {
                "titulo": options["titulo"],
                "asignatura": options["asignatura"],
                "ciclo": options["ciclo"],
                "nivel": nivel,
                "version": options["version_documento"],
                "fuente_url": options["url"],
            },
            "origen": {
                "archivo_pdf": archivo.name,
                "sha256": checksum,
                "paginas": len(lector.pages),
            },
            "fragmentos": fragmentos,
        }
        archivo_json = archivo.with_suffix(".json")
        try:
            contenido_json = json.dumps(corpus, ensure_ascii=False, indent=2)
            archivo_json.write_text(contenido_json + "\n", encoding="utf-8")
            corpus = json.loads(contenido_json)
        except (OSError, ValueError) as error:
            raise CommandError(f"No se pudo crear el JSON curricular: {error}") from error

        self.stdout.write(f"JSON estructurado guardado: {archivo_json}")
        if DocumentoCurricular.objects.filter(sha256=checksum).exists():
            self.stdout.write(self.style.WARNING("Este PDF ya está indexado en PostgreSQL; no se duplicó."))
            return

        textos = [fragmento["contenido"] for fragmento in corpus["fragmentos"]]
        vectores = crear_embeddings(textos, tipo="RETRIEVAL_DOCUMENT")
        if any(len(vector) != DIMENSIONES_EMBEDDING for vector in vectores):
            raise CommandError("La dimensión del embedding no coincide con la configuración del índice.")

        with transaction.atomic():
            documento = DocumentoCurricular.objects.create(
                titulo=options["titulo"], fuente_url=options["url"], version=options["version_documento"],
                asignatura=options["asignatura"], ciclo=options["ciclo"], nivel=nivel, sha256=checksum,
            )
            FragmentoCurricular.objects.bulk_create([
                FragmentoCurricular(
                    documento=documento,
                    numero=fragmento["numero"],
                    pagina=fragmento["pagina"],
                    texto=fragmento["contenido"],
                    embedding=vector,
                )
                for fragmento, vector in zip(corpus["fragmentos"], vectores)
            ], batch_size=100)

        self.stdout.write(self.style.SUCCESS(
            f"Indexado: {documento.titulo} — {len(corpus['fragmentos'])} fragmentos de {len(lector.pages)} páginas."
        ))


def _fragmentar(texto, *, largo=1200, solapamiento=180):
    """Divide una página en ventanas legibles; cada fragmento conserva su página."""
    texto = re.sub(r"\s+", " ", texto).strip()
    fragmentos = []
    inicio = 0
    while inicio < len(texto):
        fin = min(inicio + largo, len(texto))
        if fin < len(texto):
            corte = texto.rfind(" ", inicio + largo // 2, fin)
            if corte > inicio:
                fin = corte
        parte = texto[inicio:fin].strip()
        if parte:
            fragmentos.append(parte)
        if fin >= len(texto):
            break
        inicio = max(fin - solapamiento, inicio + 1)
    return fragmentos
