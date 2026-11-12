"""Trabajos persistentes, credenciales resueltas al ejecutar y archivos privados."""
import hashlib
import json
import uuid
from contextlib import nullcontext
from datetime import timedelta
from importlib import import_module
from pathlib import Path
from types import SimpleNamespace

from django.conf import settings
from django.contrib.auth import get_user
from django.db import transaction
from django.urls import reverse
from django.utils import timezone
from django.utils.crypto import salted_hmac

from colegio.models import TrabajoIA, InstrumentoIA, CargaAcademica, Usuario
from colegio.tenancy import institucion_activa
from .configuracion import leer_conexiones, usar_configuraciones, valor, _cifrador
from .ejecucion import usar_proveedor, registrar_operacion
from .proveedor import ErrorIA

ACTIVOS = ('pendiente', 'preparando', 'generando', 'validando')
LOCALES = ('biblioteca_sync', 'biblioteca_export')
FORMULARIOS = {'prueba': 'ia_crear_prueba', 'rubrica': 'ia_crear_rubrica',
               'material': 'ia_crear_material', 'revision': 'ia_revisar_prueba'}


def huella_conexion(proveedor):
    datos = [proveedor, valor(proveedor, 'api_key'), valor(proveedor, 'model'), valor(proveedor, 'base_url')]
    return salted_hmac('trabajo-ia-conexion', json.dumps(datos)).hexdigest()


def ruta_privada(nombre):
    base = Path(settings.IA_ARCHIVOS_PRIVADOS).resolve()
    ruta = (base / nombre).resolve()
    if ruta.parent != base or ruta.is_symlink():
        raise ErrorIA('Archivo privado no válido.')
    return ruta


def borrar_temporales(trabajo):
    for adjunto in trabajo.temporales:
        ruta_privada(adjunto['nombre']).unlink(missing_ok=True)
    trabajo.temporales = []


def crear_trabajo(request, operacion, parametros, *, instrumento=None, archivos=()):
    if not request.session.session_key:
        request.session.save()
    nombre = request.ia_proveedor
    modelo = 'Biblioteca pública · proceso local' if operacion in LOCALES else str(valor(nombre, 'model') or nombre)
    manifiesto = [{'tipo': mime, 'sha256': hashlib.sha256(datos).hexdigest()} for datos, mime in archivos]
    canon = json.dumps([operacion, nombre, modelo, parametros, manifiesto, instrumento.pk if instrumento else None], sort_keys=True)
    huella = hashlib.sha256(canon.encode()).hexdigest()
    try:
        token = uuid.UUID(request.POST.get('idempotencia', ''))
    except ValueError:
        token = uuid.uuid5(uuid.NAMESPACE_URL, request.session.session_key + huella)
    with transaction.atomic():
        trabajo, nuevo = TrabajoIA.objects.get_or_create(
            usuario=request.user, institucion=request.institucion, idempotencia=token,
            defaults={'sesion': request.session.session_key, 'huella': huella,
                      'conexion_huella': '' if operacion in LOCALES else huella_conexion(nombre), 'operacion': operacion,
                      'proveedor': nombre, 'modelo': modelo, 'parametros': parametros,
                      'instrumento': instrumento})
        if not nuevo:
            if trabajo.huella != huella:
                raise ErrorIA('Este envío ya se utilizó con otros datos. Recarga el formulario.')
            return trabajo
        try:
            for indice, (datos, mime) in enumerate(archivos):
                nombre_archivo = f'{trabajo.pk}-{indice}.bin'
                ruta = ruta_privada(nombre_archivo)
                ruta.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                ruta.write_bytes(_cifrador(crear=True).encrypt(datos))
                trabajo.temporales.append({'nombre': nombre_archivo, 'tipo': mime})
            trabajo.save(update_fields=['temporales'])
        except Exception:
            borrar_temporales(trabajo)
            raise
        transaction.on_commit(lambda: encolar(trabajo.pk))
    return trabajo


def encolar(pk):
    from colegio.tasks import ejecutar_trabajo
    try:
        ejecutar_trabajo.apply_async(args=[str(pk)], retry=False)
    except Exception:
        trabajo = TrabajoIA.objects.get(pk=pk)
        fallar(trabajo, 'No se pudo conectar con la cola. Puedes recuperar los campos y volver a intentar.')


def respuesta_trabajo(request, trabajo):
    from django.http import JsonResponse
    from django.shortcuts import redirect
    url = reverse('ia_trabajo', args=[trabajo.pk])
    if 'application/json' in request.headers.get('Accept', ''):
        return JsonResponse({'id': str(trabajo.pk), 'url': url,
                             'estado_url': reverse('ia_trabajo_estado', args=[trabajo.pk])}, status=202)
    return redirect(url)


def cambiar_etapa(trabajo, estado, mensaje):
    evento = {'etapa': estado, 'mensaje': mensaje, 'fecha': timezone.now().isoformat()}
    trabajo.actividad = [*trabajo.actividad[-19:], evento]
    cambios = {'estado': estado, 'mensaje': mensaje, 'actividad': trabajo.actividad, 'actualizado': timezone.now()}
    if not TrabajoIA.objects.filter(pk=trabajo.pk, estado__in=ACTIVOS).update(**cambios):
        raise ErrorIA('El trabajo ya terminó o fue interrumpido.')
    trabajo.estado, trabajo.mensaje = estado, mensaje


def fallar(trabajo, mensaje):
    with transaction.atomic():
        actual = TrabajoIA.objects.select_for_update().get(pk=trabajo.pk)
        if actual.estado not in ACTIVOS:
            return
        borrar_temporales(actual)
        # Los campos se conservan para el reintento, privados al propietario.
        actual.estado, actual.mensaje = 'error', mensaje[:400]
        actual.terminado = timezone.now()
        actual.save(update_fields=['estado', 'mensaje', 'terminado', 'temporales', 'parametros', 'actualizado'])


def ejecutar(pk):
    trabajo = TrabajoIA.objects.select_related('institucion').get(pk=pk)
    with institucion_activa(trabajo.institucion):
        if trabajo.estado != 'pendiente':
            return
        if timezone.now() - trabajo.creado > timedelta(minutes=5):
            fallar(trabajo, 'La operación en espera caducó. Puedes volver a intentarlo.')
            return
        if not TrabajoIA.objects.filter(pk=pk, estado='pendiente').update(estado='preparando', iniciado=timezone.now()):
            return
        trabajo.refresh_from_db()
        try:
            motor = import_module(settings.SESSION_ENGINE)
            peticion = SimpleNamespace(session=motor.SessionStore(session_key=trabajo.sesion))
            usuario = get_user(peticion)
            if (not usuario.is_authenticated or not usuario.is_active or usuario.pk != trabajo.usuario_id
                    or usuario.institucion_id != trabajo.institucion_id or not trabajo.institucion.activa
                    or usuario.tipo_usuario != 'DOCENTE'):
                raise ErrorIA('La sesión o el acceso ya no están vigentes. Vuelve a iniciar sesión.')
            peticion.user = usuario
            local = trabajo.operacion in LOCALES
            with usar_configuraciones({} if local else leer_conexiones(peticion)), usar_proveedor(trabajo.proveedor):
                if not local and (trabajo.proveedor not in ('gemini', 'qwen', 'simulado') or (
                    trabajo.proveedor == 'simulado' and settings.IA_PROVEEDOR != 'simulado')):
                    raise ErrorIA('El proveedor ya no está habilitado.')
                if not local and huella_conexion(trabajo.proveedor) != trabajo.conexion_huella:
                    raise ErrorIA('La conexión seleccionada cambió o caducó. Reconéctala y vuelve a intentar.')
                with (nullcontext() if local else registrar_operacion(usuario, trabajo.proveedor, trabajo.operacion)):
                    resultado, contenido, carga = _procesar(trabajo, usuario)
                cambiar_etapa(trabajo, 'validando', 'Validando el resultado completo antes de guardarlo.')
                with transaction.atomic():
                    actual = TrabajoIA.objects.select_for_update().get(pk=pk)
                    if actual.estado != 'validando' or timezone.now()-actual.iniciado > timedelta(minutes=5):
                        raise ErrorIA('La ejecución fue interrumpida o superó cinco minutos.')
                    if contenido is not None:
                        actual.instrumento = InstrumentoIA.objects.create(
                            docente=usuario.docente, carga=carga, tipo=trabajo.operacion.upper(),
                            titulo=contenido['titulo'], objetivo=trabajo.parametros.get('objetivo', ''),
                            parametros={k: v for k, v in trabajo.parametros.items() if k != 'carga'},
                            contenido=contenido, contenido_ia=contenido)
                    actual.resultado = resultado
                    actual.archivo = trabajo.archivo
                    borrar_temporales(actual)
                    actual.parametros.pop('texto', None)
                    actual.estado, actual.mensaje = 'completado', 'Resultado disponible para revisión.'
                    actual.terminado = timezone.now()
                    actual.save()
        except Exception as error:
            fallar(trabajo, str(error) if isinstance(error, ErrorIA) else 'No se pudo completar la operación. Recupera los campos y vuelve a intentar.')
            if trabajo.archivo:
                ruta_privada(trabajo.archivo).unlink(missing_ok=True)


def _procesar(trabajo, usuario):
    from . import asistentes, dominio
    from colegio import views_ia
    cambiar_etapa(trabajo, 'preparando', 'Comprobando permisos y preparando el contexto.')
    datos = dict(trabajo.parametros)
    if trabajo.operacion in LOCALES:
        from . import biblioteca, biblioteca_paquetes
        cambiar_etapa(trabajo, 'generando', 'Preparando la biblioteca pública sin llamadas a la IA.')
        if trabajo.operacion == 'biblioteca_sync':
            return biblioteca.sincronizar(datos['fuente'], informar=lambda m: cambiar_etapa(trabajo, 'generando', m)), None, None
        trabajo.archivo = f'{trabajo.pk}.zip'
        ruta = ruta_privada(trabajo.archivo)
        ruta.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        ruta.write_bytes(biblioteca_paquetes.exportar())
        return {'biblioteca': True}, None, None
    if trabajo.operacion in ('exportar', 'lectura'):
        instrumento = InstrumentoIA.objects.get(pk=trabajo.instrumento_id, docente__usuario=usuario,
                                               institucion_id=trabajo.institucion_id, estado='APROBADO')
        cambiar_etapa(trabajo, 'generando', 'Preparando PDF.' if trabajo.operacion == 'exportar' else 'Esperando la lectura del proveedor.')
        if trabajo.operacion == 'exportar':
            from .documentos import generar_pdf
            pdf = generar_pdf(instrumento, datos['version'])
            trabajo.archivo = f'{trabajo.pk}.pdf'
            ruta = ruta_privada(trabajo.archivo)
            ruta.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            ruta.write_bytes(pdf)
            return {}, None, None
        if datos.get('alumno') and not dominio.alumnos_de_carga(instrumento.carga).filter(pk=datos['alumno']).exists():
            raise ErrorIA('El alumno ya no pertenece a esta carga.')
        archivos = [(_cifrador().decrypt(ruta_privada(a['nombre']).read_bytes()), a['tipo']) for a in trabajo.temporales]
        lecturas = asistentes.leer_respuestas(instrumento.contenido, archivos)
        return {'lecturas': lecturas, 'alumno': datos.get('alumno', '')}, None, None
    carga = CargaAcademica.objects.select_related('curso', 'asignatura', 'periodo').get(
        pk=datos['carga'], docente__usuario=usuario, institucion_id=trabajo.institucion_id)
    datos['carga'] = carga
    contexto = dominio.contexto_carga(carga)
    mensaje = ('Esperando la respuesta del proveedor para el objetivo personalizado.'
               if trabajo.operacion == 'material' and datos.get('contexto_curricular') == 'personalizado'
               else 'Recuperando fuentes y esperando la respuesta del proveedor.')
    cambiar_etapa(trabajo, 'generando', mensaje)
    if trabajo.operacion == 'revision':
        return {'revision': asistentes.revisar_prueba(contexto, datos.get('objetivo', ''), datos['texto'])}, None, None
    generadores = {'prueba': views_ia._generar_prueba_con_rag, 'rubrica': views_ia._generar_rubrica_con_rag,
                   'material': views_ia._generar_material_con_rag}
    return {}, generadores[trabajo.operacion](contexto, datos), carga


def limpiar():
    from .biblioteca import limpiar_interrumpidas
    limpiar_interrumpidas()
    # También se ejecuta desde la consulta de estado: la UI no depende de beat para recuperarse.
    limite = timezone.now() - timedelta(minutes=5)
    for trabajo in TrabajoIA.objects.filter(estado__in=ACTIVOS, creado__lt=limite):
        referencia = trabajo.iniciado or trabajo.creado
        if referencia < limite:
            fallar(trabajo, 'La operación fue interrumpida o superó cinco minutos. Puedes volver a intentarlo.')
    # PDFs caducan tras 24 horas; documentos originales permanecen en la base.
    for trabajo in TrabajoIA.objects.exclude(archivo='').filter(terminado__lt=timezone.now()-timedelta(days=1)):
        ruta_privada(trabajo.archivo).unlink(missing_ok=True)
        trabajo.archivo = ''
        trabajo.save(update_fields=['archivo'])
    base = Path(settings.IA_ARCHIVOS_PRIVADOS)
    if base.exists():
        for ruta in base.iterdir():
            if ruta.suffix not in ('.bin', '.pdf', '.zip') or ruta.is_symlink() or not ruta.is_file():
                continue
            if timezone.now().timestamp() - ruta.stat().st_mtime > 86400:
                ruta_privada(ruta.name).unlink(missing_ok=True)
