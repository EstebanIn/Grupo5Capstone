"""Diagramas didácticos declarativos. Solo datos: nunca HTML, SVG o URL de la IA."""
import re
import unicodedata
from .proveedor import ErrorIA

TIPOS = {'ajuste': 'Redondear y ajustar', 'posicional': 'Valor posicional',
         'recta': 'Completar hasta la decena', 'grupos': 'Grupos iguales',
         'reparto': 'Repartir en grupos', 'fraccion': 'Representar una fracción'}
UBICACIONES = ('contenido', 'ejercicios', 'solucionario')
MARCADOR = re.compile(r'\[\[visual:(\d{1,2})\]\]')


def validar_visuales(datos):
    if datos is None:
        return []
    if not isinstance(datos, list) or len(datos)>6:
        raise ErrorIA('El material admite hasta seis apoyos visuales.')
    resultado, usados = [], set()
    for d in datos:
        if not isinstance(d, dict):
            raise ErrorIA('El apoyo visual necesita tipo, ubicación y cantidades.')
        tipo, ubicacion = d.get('tipo'), d.get('ubicacion', 'contenido')
        identificador, a, b = d.get('id'), d.get('a'), d.get('b')
        op = d.get('operacion', '+')
        if (tipo not in TIPOS or ubicacion not in UBICACIONES or type(identificador) is not int
                or not 1<=identificador<=6 or identificador in usados
                or type(a) is not int or type(b) is not int or not 0<=a<=999 or not 1<=b<=999
                or op not in ('+', '-', '×')):
            raise ErrorIA('Revisa el tipo, ubicación y cantidades enteras del apoyo visual.')
        if tipo=='ajuste' and (op not in ('+','-') or (op=='-' and a<b)):
            raise ErrorIA('El ajuste necesita una suma o resta con resultado no negativo.')
        if tipo=='posicional' and ((op=='-' and a<b) or (op=='×' and b>9)):
            raise ErrorIA('Usa una resta no negativa o multiplicación por un dígito.')
        if tipo=='recta':
            inicio,distancia=(a,b) if op=='+' else (b,a-b)
            if op not in ('+','-') or not 1<=distancia<=100 or inicio%10==0 or distancia<10-inicio%10 or (op=='+' and b>30):
                raise ErrorIA('La recta necesita alcanzar la próxima decena: suma hasta 30 o resta con diferencia de hasta 100.')
        if tipo=='grupos' and not (1<=a<=6 and 1<=b<=10):
            raise ErrorIA('El arreglo admite entre 1 y 6 filas y entre 1 y 10 puntos por fila.')
        if tipo=='reparto' and not (1<=a<=60 and 1<=b<=6 and a%b==0 and a//b<=10):
            raise ErrorIA('El reparto admite hasta 60 elementos, 6 grupos y 10 por grupo, sin resto.')
        if tipo=='fraccion' and not (1<=a<=b and 2<=b<=12):
            raise ErrorIA('La fracción necesita entre 2 y 12 partes y un numerador no mayor al denominador.')
        titulo = d.get('titulo', TIPOS[tipo])
        if not isinstance(titulo,str) or len(titulo)>100:
            raise ErrorIA('El título del apoyo visual debe tener hasta 100 caracteres.')
        resultado.append({'id':identificador,'tipo':tipo,'a':a,'b':b,'operacion':op,
            'ubicacion':ubicacion,'titulo':titulo.strip() or TIPOS[tipo]})
        usados.add(identificador)
    return resultado


def figura(d):
    """Geometría y resultados calculados aquí, sin confiar en respuestas del modelo."""
    a,b,tipo,op = d['a'],d['b'],d['tipo'],d['operacion']
    resuelto = d['ubicacion']!='ejercicios'
    f = {**d,'resuelto':resuelto,'tarjetas':[],'puntos':[],'cajas':[],'partes':[],'saltos':[]}
    if tipo=='ajuste':
        if op=='+':
            redondo=((a+9)//10)*10; delta=redondo-a
            valores=[(f'{a} → {redondo}',f'Agrega {delta} para redondear'),
                     (f'{redondo} + {b}',str(redondo+b) if resuelto else 'Calcula'),
                     (f'{redondo+b} − {delta}' if resuelto else f'Ajusta: resta {delta}',str(a+b) if resuelto else 'Completa')]
            formula=f'{a} + {b} = {a+b}'
        else:
            redondo=((b+9)//10)*10
            if redondo>a:redondo=(b//10)*10
            delta=redondo-b
            ajuste=f'+ {delta}' if delta>=0 else f'− {abs(delta)}'
            valores=[(f'{b} → {redondo}',f'{"Suma" if delta>=0 else "Resta"} {abs(delta)} al número que restas'),
                     (f'{a} − {redondo}',str(a-redondo) if resuelto else 'Calcula'),
                     (f'{a-redondo} {ajuste}' if resuelto else f'Ajusta: {ajuste}',str(a-b) if resuelto else 'Completa')]
            formula=f'{a} − {b} = {a-b}'
        f['tarjetas']=[{'x':10+i*193,'titulo':x,'detalle':y} for i,(x,y) in enumerate(valores)]
        f.update(formula=formula if resuelto else f'{a} {op} {b} = ______',alto=145)
    elif tipo=='posicional':
        partes_a=[(a//p%10)*p for p in (100,10,1)]
        partes_b=[(b//p%10)*p for p in (100,10,1)]
        if op=='-':
            if partes_a[2]<partes_b[2]:partes_a[1]-=10;partes_a[2]+=10
            if partes_a[1]<partes_b[1]:partes_a[0]-=100;partes_a[1]+=100
            if partes_a!=[(a//p%10)*p for p in (100,10,1)]:
                f['reagrupacion']=f'Reagrupa {a}: '+ ' + '.join(str(x) for x in partes_a)
        for i,(peso,nombre) in enumerate([(100,'Centenas'),(10,'Decenas'),(1,'Unidades')]):
            va=partes_a[i]
            vb=b if op=='×' else partes_b[i]
            parcial=va*vb if op=='×' else va+vb if op=='+' else va-vb
            f['tarjetas'].append({'x':10+i*193,'titulo':nombre,
                'detalle':f'{va} {op} {vb}', 'resultado':str(parcial) if resuelto else '______'})
        total=a*b if op=='×' else a+b if op=='+' else a-b
        if not f.get('reagrupacion'):
            f['reagrupacion']='Reúne: '+' + '.join(t['resultado'] for t in f['tarjetas'])+f' = {total}'
        f.update(formula=f'{a} {op} {b} = {total}' if resuelto else f'{a} {op} {b} = ______',alto=190)
    elif tipo=='recta':
        inicio,distancia=(a,b) if op=='+' else (b,a-b)
        gap=10-inicio%10; medio=inicio+gap; fin=inicio+distancia
        x0,x2=45,550;xm=x0+(x2-x0)*gap/distancia
        f.update(x0=x0,xm=xm,x2=x2,a=inicio,medio=medio,fin=fin,
            etiqueta_fin=str(fin) if resuelto or op=='-' else '?',gap=gap,resto=distancia-gap,
            camino1=f'M {x0} 105 Q {(x0+xm)/2} 20 {xm} 105',
            camino2=f'M {xm} 105 Q {(xm+x2)/2} 20 {x2} 105',
            etiqueta_x1=(x0+xm)/2,etiqueta_x2=(xm+x2)/2,
            formula=f'{a} {op} {b} = {distancia if op=="-" else fin}' if resuelto else f'{a} {op} {b} = ______',alto=210)
    elif tipo=='grupos':
        for fila in range(a):
            for columna in range(b):
                f['puntos'].append({'x':295-(b-1)*19+columna*38,'y':54+fila*26})
        f.update(formula=f'{a} × {b} = {a*b}' if resuelto else f'{a} × {b} = ______',
            leyenda=f'{a} {"fila" if a==1 else "filas"} de {b} {"elemento" if b==1 else "elementos"}',alto=88+a*26)
    elif tipo=='reparto':
        por_grupo=a//b
        for grupo in range(b):
            x=10+(grupo%3)*193;y=10+(grupo//3)*110
            f['cajas'].append({'x':x,'y':y,'label_x':x+86,'label_y':y+23,'numero':grupo+1})
            if resuelto:
                for n in range(por_grupo):
                    f['puntos'].append({'x':x+25+(n%5)*30,'y':y+46+(n//5)*25})
        f.update(formula=f'{a} ÷ {b} = {por_grupo}' if resuelto else f'Reparte {a} elementos en {b} grupos.',alto=45+110*((b+2)//3))
    else:
        ancho=540/b
        f['partes']=[{'x':25+i*ancho,'ancho':ancho,'llena':i<a} for i in range(b)]
        f.update(formula=f'{a} de {b} partes iguales: {a}/{b}' if resuelto else '¿Qué fracción está representada?',alto=125)
    return f


def bloques(texto, recursos, ubicacion):
    if ubicacion in ('ejercicios','solucionario'):
        encabezado=re.match(r'^\s*#{1,4}\s+([^\n]+)\n',texto or '')
        if encabezado:
            titulo=''.join(c for c in unicodedata.normalize('NFKD',encabezado[1].lower()) if not unicodedata.combining(c)).strip()
            nombres={'ejercicios','ejercicios propuestos'} if ubicacion=='ejercicios' else {'solucionario','solucionario docente','solucionario para el docente'}
            if titulo in nombres:texto=texto[encabezado.end():]
    recursos={r['id']:r for r in validar_visuales(recursos) if r['ubicacion']==ubicacion}
    partes, usados, inicio = [],set(),0
    for match in MARCADOR.finditer(texto or ''):
        if match.start()>inicio:partes.append({'texto':texto[inicio:match.start()]})
        indice=int(match[1]);inicio=match.end()
        if indice in recursos and indice not in usados:
            partes.append({'figura':figura(recursos[indice])});usados.add(indice)
    if (texto or '')[inicio:]:partes.append({'texto':texto[inicio:]})
    # Si el profesor mueve o borra un marcador al editar, el recurso no se pierde.
    partes.extend({'figura':figura(r)} for i,r in recursos.items() if i not in usados)
    return partes


def proponer_visuales(contenido):
    """Sugiere solo sobre la explicación; no toma resultados del solucionario."""
    resultado=dict(contenido); existentes=validar_visuales(resultado.get('recursos_visuales',[]))
    texto=resultado.get('contenido','');nuevos=[]
    # Se mantiene el contenido de cada sección y se inserta el diagrama al final.
    secciones=re.split(r'(?=^#{1,3}\s)',texto,flags=re.M)
    for indice,seccion in enumerate(secciones):
        if len(existentes)+len(nuevos)>=6:break
        limpia=re.sub(r'[*_`]', '', seccion)
        nombre=limpia[:220].lower()
        tipo=('ajuste' if any(x in nombre for x in ['redonde','ajust','compens']) else
              'posicional' if any(x in nombre for x in ['posicional','descompon','separar']) else
              'recta' if any(x in nombre for x in ['decena','completar']) else None)
        if not tipo:continue
        for m in re.finditer(r'(?<!\d)(\d{1,3})\s*([+−\-×x])\s*(\d{1,3})(?!\d)',limpia):
            a,op,b=int(m[1]),m[2].replace('−','-').replace('x','×'),int(m[3])
            if op=='×' and tipo!='posicional':continue
            if tipo=='ajuste' and (a if op=='+' else b)%10==0:continue
            if any((r['tipo'],r['a'],r['b'],r['operacion'])==(tipo,a,b,op) for r in existentes+nuevos):break
            rid=next(n for n in range(1,7) if n not in {r['id'] for r in existentes+nuevos})
            recurso={'id':rid,'tipo':tipo,'ubicacion':'contenido','a':a,'b':b,'operacion':op}
            try:recurso=validar_visuales([recurso])[0]
            except ErrorIA:continue
            nuevos.append(recurso)
            inicio_ejemplo=re.search(r'(?im)^\*{0,2}Ejemplo resuelto',seccion)
            if inicio_ejemplo:
                n=inicio_ejemplo.start()
                secciones[indice]=seccion[:n].rstrip()+f'\n\n[[visual:{rid}]]\n\n'+seccion[n:]
            else:secciones[indice]=seccion.rstrip()+f'\n\n[[visual:{rid}]]\n\n'
            break
        if len(nuevos)>=3:break
    resultado['contenido']=''.join(secciones)
    resultado['recursos_visuales']=existentes+nuevos
    return resultado


def visuales_desde_post(post, validar=True):
    recursos=[]
    for rid in range(1,7):
        if not post.get(f'visual_{rid}_tipo') or post.get(f'visual_{rid}_eliminar'):continue
        try:a,b=int(post.get(f'visual_{rid}_a','')),int(post.get(f'visual_{rid}_b',''))
        except ValueError:
            if validar:raise ErrorIA('Los datos del apoyo visual deben ser números enteros.') from None
            a,b=post.get(f'visual_{rid}_a',''),post.get(f'visual_{rid}_b','')
        recursos.append({'id':rid,'tipo':post[f'visual_{rid}_tipo'],'ubicacion':post.get(f'visual_{rid}_ubicacion','contenido'),
            'a':a,'b':b,'operacion':post.get(f'visual_{rid}_operacion','+'),'titulo':post.get(f'visual_{rid}_titulo','')})
    return validar_visuales(recursos) if validar else recursos
