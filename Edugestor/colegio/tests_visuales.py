from copy import deepcopy
from io import BytesIO
from unittest import mock
from django.test import SimpleTestCase
from django.template.loader import render_to_string
from django.urls import reverse
from pypdf import PdfReader

from .ia.visuales import validar_visuales, figura, bloques, proponer_visuales
from .ia.documentos import contenido_version, generar_pdf, contexto_documento
from .ia.pedagogia import validar_material
from .ia.proveedor import ErrorIA
from .tests_documentos import instrumento
from .tests import AsistenteIATestBase
from .models import InstrumentoIA
from .templatetags.ia_extras import markdown_seguro


TEXTO = ('## Redondear y ajustar\n¿Cuánto es **48 + 35**? Piensa en 50 y compensa al terminar.\n\n'
    '## Separar por valor posicional\nCalcula 456 + 237 separando centenas, decenas y unidades.\n\n'
    '## Completar hasta la decena\nPara 27 + 8, llega primero a 30 y suma lo que falta.')


def recurso(**cambios):
    return {'id':1,'tipo':'ajuste','a':48,'b':35,'operacion':'+','ubicacion':'contenido',**cambios}


class VisualesTests(SimpleTestCase):
    def test_listas_tras_un_rotulo_y_numeracion_original_se_conservan(self):
        html=str(markdown_seguro('**Sumas:**\n1. Calcula 39 + 24.\n2. Calcula 56 + 28.\n\n**Restas:**\n5. Calcula 62 - 28.\n6. Calcula 85 - 39.'))
        self.assertEqual(html.count('<ol'),2);self.assertEqual(html.count('<li>'),4)
        self.assertIn('<ol start="5">',html)
        c=validar_material({'contenido':'Ejercicios de resta','ejercicios':'**Restas:**\n5. Calcula 62 - 28.\n6. Calcula 85 - 39.',
            'separacion_revisada':True})
        texto=''.join(p.extract_text() for p in PdfReader(BytesIO(generar_pdf(instrumento('MATERIAL',c),'estudiante'))).pages)
        # Los marcadores pueden estar en un flujo PDF separado del texto del ítem.
        self.assertRegex(texto,r'(?m)^5\.\s*$')
        self.assertRegex(texto,r'(?m)^6\.\s*$')
        self.assertNotRegex(texto,r'(?m)^1\.\s*$')
        self.assertIn('Calcula 62',texto);self.assertIn('Calcula 85',texto)
    def test_sugiere_solo_ejemplos_de_explicacion_y_es_idempotente(self):
        original={'contenido':TEXTO,'ejercicios':'Calcula 99 + 24.', 'solucionario':'SECRETO 123'}
        copia=deepcopy(original);r=proponer_visuales(original)
        self.assertEqual(original,copia)
        self.assertEqual([x['tipo'] for x in r['recursos_visuales']],['ajuste','posicional','recta'])
        self.assertEqual(proponer_visuales(r),r)
        self.assertEqual({x['ubicacion'] for x in r['recursos_visuales']},{'contenido'})

    def test_ajuste_calculado_por_servidor(self):
        f=figura(validar_visuales([recurso()])[0]);self.assertEqual(f['formula'],'48 + 35 = 83')
        f=figura(validar_visuales([recurso(a=99,b=98,operacion='-')])[0])
        self.assertEqual(f['formula'],'99 − 98 = 1');self.assertEqual(f['tarjetas'][1]['detalle'],'9')

    def test_posicional_regroupa_sin_resultados_parciales_negativos(self):
        f=figura(validar_visuales([recurso(tipo='posicional',a=402,b=187,operacion='-')])[0])
        self.assertEqual([x['resultado'] for x in f['tarjetas']],['200','10','5'])
        self.assertEqual(f['formula'],'402 - 187 = 215')
        self.assertEqual(f['reagrupacion'],'Reagrupa 402: 300 + 90 + 12')

    def test_multiplicacion_posicional_calcula_cada_parte(self):
        f=figura(validar_visuales([recurso(tipo='posicional',a=124,b=3,operacion='×')])[0])
        self.assertEqual([x['resultado'] for x in f['tarjetas']],['300','60','12'])
        self.assertEqual(f['formula'],'124 × 3 = 372')

    def test_recta_conserva_proporcion_y_datos(self):
        f=figura(validar_visuales([recurso(tipo='recta',a=27,b=8)])[0])
        self.assertEqual((f['gap'],f['resto'],f['fin']),(3,5,35))
        self.assertAlmostEqual((f['xm']-f['x0'])/(f['x2']-f['x0']),3/8)

    def test_recta_resta_muestra_complemento_del_sustraendo_al_minuendo(self):
        r=validar_visuales([recurso(tipo='recta',a=82,b=55,operacion='-')])[0]
        f=figura(r)
        self.assertEqual((f['a'],f['medio'],f['fin'],f['gap'],f['resto']),(55,60,82,5,22))
        self.assertEqual(f['formula'],'82 - 55 = 27')
        sugerido=proponer_visuales({'contenido':'## Completar hasta la decena\n**Ejemplo resuelto:** 82 - 55.\nSuma 5 + 22 = 27.'})
        self.assertEqual((sugerido['recursos_visuales'][0]['a'],sugerido['recursos_visuales'][0]['b']),(82,55))
        self.assertLess(sugerido['contenido'].index('[[visual:1]]'),sugerido['contenido'].index('Ejemplo resuelto'))

    def test_referencias_se_agrupan_sin_perder_paginas_y_sin_duplicar_encabezados(self):
        c=validar_material({'contenido':'Texto','separacion_revisada':True})
        c['fuentes']=[{'titulo':'Programa','url':'https://fuente.test/programa.pdf','pagina':n} for n in [38,7,15,7]]
        contexto=contexto_documento(instrumento('MATERIAL',c),'estudiante')
        self.assertEqual(len(contexto['referencias']),1)
        self.assertEqual(contexto['referencias'][0]['paginas'],[7,15,38])
        self.assertEqual(bloques('# Ejercicios Propuestos\n\nPractica.',[],'ejercicios'),[{'texto':'\nPractica.'}])

    def test_cantidades_visual_y_fraccion(self):
        self.assertEqual(len(figura(validar_visuales([recurso(tipo='grupos',a=3,b=4)])[0])['puntos']),12)
        reparto=figura(validar_visuales([recurso(tipo='reparto',a=24,b=4)])[0])
        self.assertEqual(len(reparto['cajas']),4);self.assertEqual(len(reparto['puntos']),24)
        fraccion=figura(validar_visuales([recurso(tipo='fraccion',a=3,b=8)])[0])
        self.assertEqual(sum(x['llena'] for x in fraccion['partes']),3)

    def test_limites_tipos_y_duplicados(self):
        for cambios in [{'tipo':'http://malicioso.test'}, {'a':True},{'a':-1},{'a':1000},
            {'tipo':'grupos','a':500},{'tipo':'reparto','a':25,'b':4},{'tipo':'fraccion','a':5,'b':4},
            {'tipo':'recta','a':20,'b':8},{'ubicacion':'oculto'}]:
            with self.subTest(cambios=cambios),self.assertRaises(ErrorIA):validar_visuales([recurso(**cambios)])
        with self.assertRaises(ErrorIA):validar_visuales([recurso(),recurso()])

    def test_diagrama_de_ejercicio_no_expone_resultado(self):
        for tipo,a,b in [('ajuste',48,35),('posicional',124,3),('recta',27,8),('reparto',24,4),('fraccion',3,8)]:
            op='×' if tipo=='posicional' else '+'
            f=figura(validar_visuales([recurso(tipo=tipo,a=a,b=b,operacion=op,ubicacion='ejercicios')])[0])
            self.assertFalse(f['resuelto'])
            if tipo=='reparto':self.assertEqual(f['puntos'],[])
            if tipo=='recta':self.assertEqual(f['etiqueta_fin'],'?')
            if tipo=='posicional':self.assertEqual({t['resultado'] for t in f['tarjetas']},{'______'})

    def test_solo_graficos_del_servidor_y_texto_escapado(self):
        recursos=validar_visuales([recurso(titulo='<script>alert(1)</script>',url='https://malicioso.test/a.svg')])
        self.assertNotIn('url',recursos[0])
        html=render_to_string('colegio/ia/_material_visual.html',{'bloques':bloques('[[visual:1]]',recursos,'contenido')})
        self.assertIn('<svg',html);self.assertNotIn('<script>',html);self.assertNotIn('malicioso.test',html)

    def test_pauta_visual_se_elimina_antes_de_renderizar_estudiante(self):
        c=validar_material({'titulo':'Visual','contenido':'Explicación [[visual:1]]','ejercicios':'Practica',
            'solucionario':'SECRETO_PAUTA [[visual:2]]','separacion_revisada':True,
            'recursos_visuales':[recurso(),recurso(id=2,titulo='SECRETO_VISUAL',ubicacion='solucionario')]})
        i=instrumento('MATERIAL',c);proyeccion=contenido_version(i,'estudiante')
        self.assertEqual(len(proyeccion['recursos_visuales']),1)
        pdf=PdfReader(BytesIO(generar_pdf(i,'estudiante')))
        texto=''.join(p.extract_text() for p in pdf.pages)
        self.assertNotIn('SECRETO',texto);self.assertIn('Redondear y ajustar',texto);self.assertIn('83',texto)
        docente=''.join(p.extract_text() for p in PdfReader(BytesIO(generar_pdf(i,'docente'))).pages)
        self.assertIn('SECRETO_VISUAL',docente)

    def test_svg_no_consulta_la_red_ni_recursos_privados(self):
        c=validar_material({'contenido':'[[visual:1]]','separacion_revisada':True,'recursos_visuales':[recurso()]})
        with mock.patch('colegio.ia.documentos.recurso_local',side_effect=AssertionError('Recurso externo')) as fetcher:
            self.assertTrue(generar_pdf(instrumento('MATERIAL',c),'estudiante').startswith(b'%PDF'))
        fetcher.assert_not_called()


class VisualesEditorTests(AsistenteIATestBase):
    def setUp(self):
        super().setUp();self.client.force_login(self.usuario_docente)
        c=validar_material({'titulo':'Cálculo mental','contenido':TEXTO,'ejercicios':'Calcula 54 + 17.',
            'solucionario':'71','separacion_revisada':False})
        self.i=InstrumentoIA.objects.create(docente=self.docente,carga=self.carga,tipo='MATERIAL',
            titulo=c['titulo'],contenido=c,contenido_ia=deepcopy(c))

    def post(self,**cambios):
        return self.client.post(reverse('ia_instrumento',args=[self.i.pk]),{**self.i.contenido,**cambios})

    def test_proponer_conserva_original_y_no_aprueba(self):
        original=deepcopy(self.i.contenido_ia)
        self.assertEqual(self.post(accion='proponer_visuales').status_code,302)
        self.i.refresh_from_db();self.assertEqual(self.i.contenido_ia,original)
        self.assertEqual(self.i.estado,'BORRADOR');self.assertEqual(len(self.i.contenido['recursos_visuales']),3)
        pagina=self.client.get(reverse('ia_instrumento',args=[self.i.pk]))
        self.assertContains(pagina,'data-recurso-id="1"');self.assertContains(pagina,'<svg')

    def test_anadir_y_editar_diagrama(self):
        self.post(accion='agregar_visual',nuevo_visual_tipo='grupos',nuevo_visual_a=3,nuevo_visual_b=4)
        self.i.refresh_from_db();self.assertEqual(len(self.i.contenido['recursos_visuales']),1)
        self.post(accion='guardar',visual_1_tipo='grupos',visual_1_a=4,visual_1_b=5,
            visual_1_ubicacion='ejercicios',visual_1_titulo='Observa el arreglo')
        self.i.refresh_from_db();self.assertEqual(self.i.contenido['recursos_visuales'][0]['a'],4)

    def test_error_conserva_campos_visuales_sin_corromper_guardado(self):
        pagina=self.post(accion='guardar',visual_1_tipo='grupos',visual_1_a=500,visual_1_b=4)
        self.assertEqual(pagina.status_code,200);self.assertContains(pagina,'value="500"')
        self.i.refresh_from_db();self.assertNotIn('recursos_visuales',self.i.contenido)

    def test_aprobado_no_se_modifica_y_copia_retiene_visuales(self):
        self.i.contenido=proponer_visuales(self.i.contenido);self.i.estado='APROBADO';self.i.save()
        anterior=deepcopy(self.i.contenido)
        self.post(accion='proponer_visuales');self.i.refresh_from_db();self.assertEqual(self.i.contenido,anterior)
        self.client.post(reverse('ia_copiar',args=[self.i.pk]))
        copia=InstrumentoIA.objects.exclude(pk=self.i.pk).get()
        self.assertEqual(copia.contenido['recursos_visuales'],anterior['recursos_visuales'])
        self.assertFalse(copia.contenido['separacion_revisada'])
