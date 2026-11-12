from copy import deepcopy
from io import BytesIO
from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase
from django.template.loader import render_to_string
from pypdf import PdfReader

from .ia.documentos import contenido_version, generar_pdf, recurso_local
from .ia.ejemplos import RUBRICA_MA04
from .ia.pedagogia import validar_rubrica, validar_material, revisar_rubrica
from .ia.proveedor import ErrorIA
from .templatetags.ia_extras import markdown_seguro


def instrumento(tipo, contenido):
    return SimpleNamespace(tipo=tipo, titulo='Caso QA', contenido=contenido, objetivo='Objetivo personalizado',
        institucion=SimpleNamespace(nombre='Colegio sintético'), carga=SimpleNamespace(curso='4° A',
            asignatura=SimpleNamespace(nombre_asignatura='Matemática')))


class DocumentosTests(SimpleTestCase):
    def test_proyeccion_estudiantil_no_contiene_campos_de_pauta(self):
        original = {'preguntas':[{'enunciado':'124 × 3', 'alternativas':['100','200','372','400'],
                                  'correcta':2,'explicacion':'SECRETO_PAUTA'}]}
        copia = deepcopy(original)
        i = instrumento('PRUEBA', original)
        c = contenido_version(i, 'estudiante')
        self.assertNotIn('correcta', c['preguntas'][0]); self.assertNotIn('explicacion',c['preguntas'][0])
        self.assertEqual(original,copia)
        html = render_to_string('colegio/ia/documento.html', {'documento':c,'instrumento':i,'version':'estudiante'})
        self.assertNotIn('SECRETO_PAUTA', html)

    def test_material_conserva_ejemplo_resuelto_sin_solucionario(self):
        i=instrumento('MATERIAL', {'titulo':'Guía', 'contenido':'Ejemplo: 12 × 3 = 36',
             'ejercicios':'Calcula 124 × 3', 'solucionario':'SECRETO_372', 'version_estructura':2,'separacion_revisada':True})
        c=contenido_version(i,'estudiante')
        self.assertIn('36',c['contenido']);self.assertNotIn('solucionario',c)
        self.assertIn('SECRETO',contenido_version(i,'docente')['solucionario'])

    def test_legacy_requiere_copia_y_revision(self):
        i=instrumento('MATERIAL',{'texto':'Texto antiguo con respuestas'})
        with self.assertRaises(ErrorIA):contenido_version(i,'estudiante')
        self.assertTrue(contenido_version(i,'docente')['contenido'])

    def test_markdown_y_fetcher_bloquean_ejecucion_y_recursos_privados(self):
        html=str(markdown_seguro('[x](javascript:alert(1)) ![img](http://127.0.0.1/secret) <script>run()</script>'))
        self.assertNotIn('href="javascript:',html);self.assertNotIn('<img',html);self.assertNotIn('<script>',html)
        for url in ('https://example.com/a.png','file:///etc/passwd','data:image/png;base64,a'):
            with self.subTest(url=url), self.assertRaises(ValueError):recurso_local(url)

    def test_pdf_a4_y_no_incluye_respuestas(self):
        i=instrumento('PRUEBA',{'preguntas':[{'enunciado':'Calcula 124 × 3','alternativas':['100','200','372','400'],
                                          'correcta':2,'explicacion':'SECRETO_PAUTA'}]})
        r=PdfReader(BytesIO(generar_pdf(i,'estudiante')))
        self.assertAlmostEqual(float(r.pages[0].mediabox.width),595.28,places=0)
        self.assertNotIn('SECRETO_PAUTA',''.join(p.extract_text() for p in r.pages))

    def test_rubrica_total_y_orientation_servidor(self):
        datos=deepcopy(RUBRICA_MA04);datos['puntaje_total']=999
        datos['criterios'][0]['puntaje_maximo']=999
        c=validar_rubrica(datos)
        self.assertEqual(c['puntaje_total'],16);self.assertEqual(c['puntajes'],[4,3,2,1])
        self.assertEqual(c['sin_evidencia']['puntaje'],0)
        r=PdfReader(BytesIO(generar_pdf(instrumento('RUBRICA',c),'estudiante')))
        self.assertGreater(r.pages[0].mediabox.width,r.pages[0].mediabox.height)
        self.assertEqual(len(revisar_rubrica(c,'')),5)

    def test_rechaza_escala_ambigua_vinculos_y_descriptores_duplicados(self):
        for puntos in ([4,4,2,1],[1,2,3,4],[4,3,2,0],[4,3,2,'1'],[4,3,2]):
            c=deepcopy(RUBRICA_MA04);c['puntajes']=puntos
            with self.subTest(puntos=puntos), self.assertRaises(ErrorIA):validar_rubrica(c)
        c=deepcopy(RUBRICA_MA04);c['criterios'][0]['evidencia']=''
        with self.assertRaises(ErrorIA):validar_rubrica(c)
        c=deepcopy(RUBRICA_MA04);c['criterios'][0]['descriptores']=['Igual']*4
        with self.assertRaises(ErrorIA):validar_rubrica(c)

    def test_tres_niveles_escala_tres_dos_uno(self):
        c=deepcopy(RUBRICA_MA04);c['niveles']=c['niveles'][:3]
        for criterio in c['criterios']:criterio['descriptores']=criterio['descriptores'][:3]
        c=validar_rubrica(c)
        self.assertEqual(c['puntajes'],[3,2,1]);self.assertEqual(c['puntaje_total'],12)
