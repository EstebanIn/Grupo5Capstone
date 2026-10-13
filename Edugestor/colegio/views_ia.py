"""
Vistas de los asistentes de IA: asistente docente y tutor del alumno.
"""

from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Count
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .ia import asistentes, dominio
from .ia.formularios import (
    FormularioMaterial,
    FormularioPrueba,
    FormularioRevision,
    FormularioRubrica,
    FormularioTutor,
)
from .ia.proveedor import ErrorIA, proveedor_activo
from .models import Alumno, CorreccionPrueba, Docente, Evaluacion, InstrumentoIA, Nota
from .views import redireccionar_por_rol


def solo_rol(tipo_usuario):
    def decorador(vista):
        @wraps(vista)
        @login_required
        def envoltura(request, *args, **kwargs):
            if request.user.tipo_usuario != tipo_usuario:
                return redireccionar_por_rol(request.user)
            return vista(request, *args, **kwargs)
        return envoltura
    return decorador


def _contexto_base(request, **extra):
    return {"modo_simulado": proveedor_activo() != "gemini", **extra}


# ============================================================
# ASISTENTE DOCENTE
# ============================================================
@solo_rol("DOCENTE")
def asistente_docente(request):
    docente = get_object_or_404(Docente, usuario=request.user)
    instrumentos = InstrumentoIA.objects.filter(docente=docente).select_related("carga__curso", "carga__asignatura")
    aprobados = instrumentos.filter(estado=InstrumentoIA.ESTADO_APROBADO)

    return render(request, "colegio/ia/asistente_docente.html", _contexto_base(
        request,
        docente=docente,
        instrumentos=instrumentos[:30],
        total_generados=instrumentos.count(),
        total_aprobados=aprobados.count(),
        promedio_corregido=aprobados.aggregate(promedio=Avg("porcentaje_corregido"))["promedio"],
    ))


def _crear_instrumento(request, *, formulario_clase, tipo, plantilla, generar):
    docente = get_object_or_404(Docente, usuario=request.user)
    formulario = formulario_clase(request.POST or None, docente=docente)

    if request.method == "POST" and formulario.is_valid():
        datos = formulario.cleaned_data
        contexto = dominio.contexto_carga(datos["carga"])
        try:
            contenido = generar(contexto, datos)
        except ErrorIA as error:
            messages.error(request, str(error))
        else:
            instrumento = InstrumentoIA.objects.create(
                docente=docente,
                carga=datos["carga"],
                tipo=tipo,
                titulo=contenido["titulo"],
                objetivo=datos.get("objetivo", ""),
                parametros={clave: valor for clave, valor in datos.items() if clave not in ("carga", "objetivo")},
                contenido_ia=contenido,
                contenido=contenido,
            )
            messages.success(request, "Borrador generado. Revísalo y corrige lo necesario antes de aprobarlo.")
            return redirect("ia_instrumento", pk=instrumento.pk)

    return render(request, plantilla, _contexto_base(request, docente=docente, form=formulario))


@solo_rol("DOCENTE")
def ia_crear_prueba(request):
    return _crear_instrumento(
        request, formulario_clase=FormularioPrueba, tipo=InstrumentoIA.TIPO_PRUEBA,
        plantilla="colegio/ia/crear_prueba.html",
        generar=lambda contexto, d: asistentes.crear_prueba(
            contexto, d["objetivo"], d["tema"], d["cantidad"], d["dificultad"]),
    )


@solo_rol("DOCENTE")
def ia_crear_rubrica(request):
    return _crear_instrumento(
        request, formulario_clase=FormularioRubrica, tipo=InstrumentoIA.TIPO_RUBRICA,
        plantilla="colegio/ia/crear_rubrica.html",
        generar=lambda contexto, d: asistentes.crear_rubrica(
            contexto, d["objetivo"], d["actividad"], d["criterios"], d["niveles"]),
    )


@solo_rol("DOCENTE")
def ia_crear_material(request):
    return _crear_instrumento(
        request, formulario_clase=FormularioMaterial, tipo=InstrumentoIA.TIPO_MATERIAL,
        plantilla="colegio/ia/crear_material.html",
        generar=lambda contexto, d: asistentes.crear_material(
            contexto, d["objetivo"], d["tema"], d["tipo"]),
    )


@solo_rol("DOCENTE")
def ia_revisar_prueba(request):
    docente = get_object_or_404(Docente, usuario=request.user)
    inicial = {}
    if request.GET.get("instrumento"):
        # Revisar la calidad de un borrador creado con el asistente, sin copiar y pegar.
        prueba = get_object_or_404(InstrumentoIA, pk=request.GET["instrumento"], docente=docente,
                                   tipo=InstrumentoIA.TIPO_PRUEBA)
        inicial = {"carga": prueba.carga, "objetivo": prueba.objetivo,
                   "texto": asistentes.texto_de_prueba(prueba.contenido, con_pauta=True)}
    formulario = FormularioRevision(request.POST or None, docente=docente, initial=inicial)
    revision = None

    if request.method == "POST" and formulario.is_valid():
        datos = formulario.cleaned_data
        try:
            revision = asistentes.revisar_prueba(
                dominio.contexto_carga(datos["carga"]), datos["objetivo"], datos["texto"])
        except ErrorIA as error:
            messages.error(request, str(error))

    return render(request, "colegio/ia/revisar_prueba.html", _contexto_base(
        request, docente=docente, form=formulario, revision=revision))


def _contenido_desde_post(tipo, post):
    """Reconstruye el contenido editado por el docente a partir del formulario."""
    if tipo == InstrumentoIA.TIPO_PRUEBA:
        indices = sorted({int(clave[1:].split("_")[0]) for clave in post if clave.endswith("_enunciado")})
        preguntas = [
            {
                "enunciado": post.get(f"p{i}_enunciado", ""),
                "alternativas": [post.get(f"p{i}_alt{j}", "") for j in range(4)],
                "correcta": post.get(f"p{i}_correcta", "0"),
                "explicacion": post.get(f"p{i}_explicacion", ""),
            }
            for i in indices if not post.get(f"p{i}_eliminar")
        ]
        return asistentes.validar_prueba({
            "titulo": post.get("titulo", ""), "instrucciones": post.get("instrucciones", ""),
            "preguntas": preguntas,
        })

    if tipo == InstrumentoIA.TIPO_RUBRICA:
        niveles = [post[clave] for clave in sorted(
            (c for c in post if c.startswith("nivel_")), key=lambda c: int(c.split("_")[1]))]
        indices = sorted({int(clave[1:].split("_")[0]) for clave in post if clave.endswith("_criterio")})
        criterios = [
            {
                "criterio": post.get(f"c{i}_criterio", ""),
                "puntaje_maximo": post.get(f"c{i}_puntaje") or len(niveles),
                "descriptores": [post.get(f"c{i}_d{j}", "") for j in range(len(niveles))],
            }
            for i in indices if not post.get(f"c{i}_eliminar")
        ]
        return asistentes.validar_rubrica({
            "titulo": post.get("titulo", ""), "descripcion": post.get("descripcion", ""),
            "niveles": niveles, "criterios": criterios,
        })

    texto = post.get("texto", "").strip()
    if not texto:
        raise ErrorIA("El material no puede quedar vacío.")
    return {"titulo": post.get("titulo", "").strip()[:200] or "Material de estudio", "texto": texto}


@solo_rol("DOCENTE")
def ia_instrumento(request, pk):
    docente = get_object_or_404(Docente, usuario=request.user)
    instrumento = get_object_or_404(
        InstrumentoIA.objects.select_related("carga__curso", "carga__asignatura"), pk=pk, docente=docente)

    if request.method == "POST" and instrumento.estado == InstrumentoIA.ESTADO_BORRADOR:
        try:
            contenido = _contenido_desde_post(instrumento.tipo, request.POST)
        except ErrorIA as error:
            messages.error(request, f"No se guardó: {error} Revisa que no queden campos vacíos.")
        else:
            instrumento.contenido = contenido
            instrumento.titulo = contenido["titulo"]
            if request.POST.get("accion") == "aprobar":
                instrumento.estado = InstrumentoIA.ESTADO_APROBADO
                instrumento.fecha_aprobacion = timezone.now()
                instrumento.porcentaje_corregido = asistentes.porcentaje_corregido(
                    instrumento.tipo, instrumento.contenido_ia, contenido)
                messages.success(
                    request, f"Aprobado. Corregiste el {instrumento.porcentaje_corregido}% del borrador.")
            else:
                messages.success(request, "Cambios guardados.")
            instrumento.save()
            return redirect("ia_instrumento", pk=instrumento.pk)

    return render(request, "colegio/ia/instrumento.html", _contexto_base(
        request, docente=docente, instrumento=instrumento, contenido=instrumento.contenido,
        editable=instrumento.estado == InstrumentoIA.ESTADO_BORRADOR))


@solo_rol("DOCENTE")
@require_POST
def ia_eliminar_instrumento(request, pk):
    docente = get_object_or_404(Docente, usuario=request.user)
    instrumento = get_object_or_404(InstrumentoIA, pk=pk, docente=docente)
    instrumento.delete()
    messages.success(request, "Instrumento eliminado.")
    return redirect("asistente_docente")


# ============================================================
# TUTOR DEL ALUMNO
# ============================================================
def _clave_historial(asignatura):
    return f"tutor_historial_{asignatura.pk}"


@solo_rol("ALUMNO")
def tutor_alumno(request):
    alumno = get_object_or_404(Alumno, usuario=request.user)
    asignaturas = dominio.asignaturas_alumno(alumno)

    asignatura = None
    asignatura_id = request.GET.get("asignatura") or request.POST.get("asignatura")
    if asignatura_id:
        asignatura = get_object_or_404(asignaturas, pk=asignatura_id)
    elif asignaturas:
        asignatura = asignaturas[0]

    historial = request.session.get(_clave_historial(asignatura), []) if asignatura else []
    formulario = FormularioTutor(request.POST or None)

    if request.method == "POST" and asignatura:
        if request.POST.get("accion") == "nueva":
            request.session.pop(_clave_historial(asignatura), None)
            return redirect(f"{request.path}?asignatura={asignatura.pk}")

        if formulario.is_valid():
            mensaje = formulario.cleaned_data["mensaje"].strip()
            try:
                respuesta = asistentes.responder_tutor(dominio.contexto_tutor(asignatura), historial, mensaje)
            except ErrorIA as error:
                messages.error(request, str(error))
            else:
                historial = (historial + [
                    {"rol": "usuario", "texto": mensaje},
                    {"rol": "modelo", "texto": respuesta},
                ])[-2 * asistentes.MAX_MENSAJES_HISTORIAL:]
                request.session[_clave_historial(asignatura)] = historial
                return redirect(f"{request.path}?asignatura={asignatura.pk}#ultimo")

    return render(request, "colegio/ia/tutor_alumno.html", _contexto_base(
        request, alumno=alumno, asignaturas=asignaturas, asignatura=asignatura,
        historial=historial, form=formulario))


# ============================================================
# CORREGIR PRUEBAS RESPONDIDAS POR ALUMNOS
# ============================================================
TIPOS_HOJA_PERMITIDOS = {"image/jpeg", "image/png", "image/webp", "image/heic", "application/pdf"}
MAX_ARCHIVOS_HOJA = 5
MAX_BYTES_HOJA = 10 * 1024 * 1024


def _prueba_del_docente(request, pk):
    docente = get_object_or_404(Docente, usuario=request.user)
    instrumento = get_object_or_404(
        InstrumentoIA.objects.select_related("carga__curso", "carga__asignatura", "carga__periodo"),
        pk=pk, docente=docente, tipo=InstrumentoIA.TIPO_PRUEBA,
    )
    return docente, instrumento


@solo_rol("DOCENTE")
def ia_corregir(request):
    """Elegir cuál prueba aprobada se va a corregir."""
    docente = get_object_or_404(Docente, usuario=request.user)
    pruebas = (
        InstrumentoIA.objects.filter(docente=docente, tipo=InstrumentoIA.TIPO_PRUEBA)
        .select_related("carga__curso", "carga__asignatura")
        .annotate(total_correcciones=Count("correcciones"))
    )
    return render(request, "colegio/ia/corregir.html", _contexto_base(
        request, docente=docente,
        aprobadas=[p for p in pruebas if p.estado == InstrumentoIA.ESTADO_APROBADO],
        borradores=[p for p in pruebas if p.estado == InstrumentoIA.ESTADO_BORRADOR],
    ))


def _leer_archivos(request):
    """Valida los archivos subidos y los retorna como [(bytes, mime)]. No se guardan en disco."""
    archivos = request.FILES.getlist("archivos")
    if not archivos:
        raise ErrorIA("Sube al menos una foto o PDF de la prueba respondida.")
    if len(archivos) > MAX_ARCHIVOS_HOJA:
        raise ErrorIA(f"Puedes subir hasta {MAX_ARCHIVOS_HOJA} archivos por prueba.")
    leidos = []
    for archivo in archivos:
        if archivo.content_type not in TIPOS_HOJA_PERMITIDOS:
            raise ErrorIA(f"El archivo {archivo.name} no es una imagen (JPG, PNG, WEBP, HEIC) ni un PDF.")
        if archivo.size > MAX_BYTES_HOJA:
            raise ErrorIA(f"El archivo {archivo.name} pesa más de 10 MB.")
        leidos.append((archivo.read(), archivo.content_type))
    return leidos


@solo_rol("DOCENTE")
def ia_corregir_prueba(request, pk):
    """
    Paso 1: elegir alumno y subir la hoja (o ingresar las respuestas a mano).
    Paso 2: el docente confirma o ajusta las respuestas leídas y se calcula la nota.
    """
    docente, instrumento = _prueba_del_docente(request, pk)
    if instrumento.estado != InstrumentoIA.ESTADO_APROBADO:
        messages.error(request, "Aprueba la prueba antes de corregir: la pauta tiene que ser la definitiva.")
        return redirect("ia_instrumento", pk=instrumento.pk)

    preguntas = instrumento.contenido["preguntas"]
    alumnos = dominio.alumnos_de_carga(instrumento.carga)
    contexto = _contexto_base(
        request, docente=docente, instrumento=instrumento, alumnos=alumnos,
        correcciones=instrumento.correcciones.select_related("alumno")[:50],
        paso="subir",
    )

    if request.method == "GET" and request.GET.get("manual"):
        lecturas = [{"pregunta": n, "marcada": None, "estado": "manual", "observacion": ""}
                    for n in range(1, len(preguntas) + 1)]
        contexto.update(paso="confirmar", filas=list(zip(preguntas, lecturas)),
                        alumno_id=request.GET.get("alumno", ""), leida_con_ia=False)

    elif request.method == "POST" and request.POST.get("accion") == "leer":
        try:
            lecturas = asistentes.leer_respuestas(instrumento.contenido, _leer_archivos(request))
        except ErrorIA as error:
            messages.error(request, str(error))
        else:
            contexto.update(paso="confirmar", filas=list(zip(preguntas, lecturas)), leida_con_ia=True,
                            alumno_id=request.POST.get("alumno", ""),
                            por_revisar=sum(1 for l in lecturas if l["estado"] != "respondida"))

    elif request.method == "POST" and request.POST.get("accion") == "calcular":
        respuestas, ajustes = [], 0
        for numero in range(1, len(preguntas) + 1):
            valor = request.POST.get(f"r{numero}", "")
            respuestas.append(int(valor) if valor in ("0", "1", "2", "3") else None)
            leida = request.POST.get(f"ia{numero}")
            if leida is not None and leida != valor:
                ajustes += 1

        resultado = asistentes.corregir_respuestas(instrumento.contenido, respuestas)
        alumno = alumnos.filter(pk=request.POST.get("alumno") or None).first()
        correccion = CorreccionPrueba.objects.create(
            instrumento=instrumento,
            alumno=alumno,
            respuestas=resultado["detalle"],
            correctas=resultado["correctas"],
            total=resultado["total"],
            nota=resultado["nota"],
            leida_con_ia=request.POST.get("leida_con_ia") == "1",
            ajustes_docente=ajustes,
        )
        return redirect("ia_correccion", pk=correccion.pk)

    return render(request, "colegio/ia/corregir_prueba.html", contexto)


@solo_rol("DOCENTE")
def ia_correccion(request, pk):
    docente = get_object_or_404(Docente, usuario=request.user)
    correccion = get_object_or_404(
        CorreccionPrueba.objects.select_related(
            "instrumento__carga__curso", "instrumento__carga__asignatura",
            "alumno", "nota_registrada__evaluacion"),
        pk=pk, instrumento__docente=docente,
    )
    instrumento = correccion.instrumento
    evaluaciones = Evaluacion.objects.filter(carga=instrumento.carga).order_by("numero_evaluacion")

    if request.method == "POST" and correccion.alumno:
        evaluacion = evaluaciones.filter(pk=request.POST.get("evaluacion") or None).first()
        if evaluacion is None:
            messages.error(request, "Elige la evaluación del libro donde registrar la nota.")
        else:
            nota, _ = Nota.objects.update_or_create(
                evaluacion=evaluacion, alumno=correccion.alumno,
                defaults={"valor_nota": correccion.nota,
                          "observacion": f"Corregida con el Asistente IA: {instrumento.titulo}"},
            )
            correccion.nota_registrada = nota
            correccion.save(update_fields=["nota_registrada"])
            messages.success(request, f"Nota {correccion.nota} registrada en {evaluacion.nombre_evaluacion}.")
            return redirect("ia_correccion", pk=correccion.pk)

    preguntas = instrumento.contenido["preguntas"]
    detalle = [
        {"numero": numero, "pregunta": pregunta, **item}
        for numero, (pregunta, item) in enumerate(zip(preguntas, correccion.respuestas), 1)
    ]
    return render(request, "colegio/ia/correccion.html", _contexto_base(
        request, docente=docente, correccion=correccion, instrumento=instrumento, detalle=detalle,
        omitidas=sum(1 for item in detalle if item["estado"] == "omitida"),
        incorrectas=sum(1 for item in detalle if item["estado"] == "incorrecta"),
        porcentaje=round(100 * correccion.correctas / correccion.total, 1) if correccion.total else 0,
        evaluaciones=evaluaciones,
    ))
