from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from colegio.models import RegistroIA
from .indice_qwen import estado_indices
from django.http import HttpResponseForbidden
from django.utils import timezone
from django.views.decorators.debug import sensitive_post_parameters, sensitive_variables
from django.views.decorators.cache import never_cache
from .configuracion import (PROVEEDORES, estado_publico, guardar_conexion, quitar_conexion,
                            usar_configuraciones, valor)
from .ejecucion import registrar_operacion, usar_proveedor
from .forms_conexion import ConexionIAForm, ConsultaModelosForm
from .proveedor import generar, ErrorIA

def _permitido(user):
    return user.tipo_usuario in ('DOCENTE','ALUMNO')


def _conexion_segura(request):
    from urllib.parse import urlsplit
    return request.is_secure() or urlsplit('http://' + request.get_host()).hostname in ('localhost', '127.0.0.1', '::1')

@login_required
@require_POST
def seleccionar_proveedor(request):
    if not _permitido(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()
    proveedor = request.POST.get('proveedor')
    if proveedor not in ('gemini','qwen'):
        messages.error(request,'Selecciona Gemini o Qwen.')
    else:
        request.session['ia_proveedor'] = proveedor
        messages.success(request,'Proveedor seleccionado: '+('Qwen' if proveedor=='qwen' else 'Gemini')+'. Se aplicará a las próximas operaciones.')
    destino=request.POST.get('next','')
    if not destino.startswith('/') or destino.startswith('//') or not url_has_allowed_host_and_scheme(destino,allowed_hosts={request.get_host()}):
        destino=reverse('registro_ia')
    return redirect(destino)

@login_required
def registro_ia(request, pk=None):
    if not _permitido(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()
    return _mostrar_registro(request, pk=pk)


def _mostrar_registro(request, pk=None, formulario_error=None, proveedor_error=None, status=200):
    # Solo datos públicos de conexión; ninguna clave se incorpora al contexto.
    conexiones = []
    for nombre in PROVEEDORES:
        estado = estado_publico(nombre)
        estado['formulario'] = formulario_error if nombre == proveedor_error else ConexionIAForm(
            proveedor=nombre, prefix=nombre, initial={'model': estado['modelo'], 'base_url': estado['base_url']})
        conexiones.append(estado)
    registros=RegistroIA.objects.filter(usuario=request.user)
    registro=get_object_or_404(registros,pk=pk) if pk else None
    return render(request,'colegio/ia/registro.html',{'registros':registros[:50], 'registro':registro,'indices':estado_indices(),
        'conexiones': conexiones, 'qwen_configurado': conexiones[1]['configurado'],
        'gemini_configurado': conexiones[0]['configurado']}, status=status)


@sensitive_post_parameters('gemini-api_key', 'qwen-api_key')
@login_required
@require_POST
@sensitive_variables()
def configurar_conexion(request, proveedor):
    if not _permitido(request.user):
        return HttpResponseForbidden()
    if proveedor not in PROVEEDORES:
        from django.http import HttpResponseBadRequest
        return HttpResponseBadRequest('Proveedor no válido.')
    # HTTP solo para el desarrollo en loopback. En un servidor se exige HTTPS.
    if not _conexion_segura(request):
        return HttpResponseForbidden('Usa HTTPS para configurar una conexión de IA.')
    if request.POST.get('accion') == 'servidor':
        quitar_conexion(request, proveedor)
        messages.success(request, 'Se quitó tu conexión personal. Se usará la configuración del servidor para ' + proveedor.title() + '.')
        return redirect(reverse('registro_ia') + '#conexiones-ia')
    formulario = ConexionIAForm(request.POST, proveedor=proveedor, prefix=proveedor)
    if formulario.is_valid():
        configuracion = dict(formulario.cleaned_data)
        if proveedor == 'gemini':
            # El modelo elegido se respeta también cuando está saturado.
            configuracion['modelos_respaldo'] = []
        candidatas = dict(request.ia_conexiones)
        candidatas[proveedor] = {**configuracion, 'timeout': 20, 'intentos': 1}
        try:
            with usar_configuraciones(candidatas), usar_proveedor(proveedor), registrar_operacion(request.user, proveedor, 'Comprobar conexión'):
                respuesta = generar('Comprueba la conexión. Devuelve exactamente {"estado":"ok"}.',
                    [{'rol':'usuario','texto':'Responde con el objeto JSON solicitado.'}], ejemplo={}, formato_json=True, temperatura=0)
                if not isinstance(respuesta, dict) or respuesta.get('estado') != 'ok':
                    raise ErrorIA('El modelo respondió, pero no completó la comprobación JSON. Revisa el modelo e intenta nuevamente.')
            configuracion['verificada'] = timezone.now().isoformat(timespec='seconds')
            guardar_conexion(request, proveedor, configuracion)
        except ErrorIA as error:
            formulario.add_error(None, str(error))
        except Exception:
            # Ni errores de almacenamiento ni SDK deben mostrar la clave o el cuerpo HTTP.
            formulario.add_error(None, 'No se pudo guardar la conexión de forma segura. Intenta nuevamente o consulta al administrador.')
        else:
            request.session['ia_proveedor'] = proveedor
            messages.success(request, proveedor.title() + ': conexión comprobada y seleccionada para tu sesión.')
            return redirect(reverse('registro_ia') + '#conexiones-ia')
    return _mostrar_registro(request, formulario_error=formulario, proveedor_error=proveedor, status=400)


@never_cache
@sensitive_post_parameters('gemini-api_key', 'qwen-api_key')
@login_required
@require_POST
@sensitive_variables()
def consultar_modelos(request, proveedor):
    from django.http import JsonResponse
    from .catalogo_modelos import listar_modelos
    if not _permitido(request.user) or not _conexion_segura(request):
        return JsonResponse({'error': 'No tienes acceso o se requiere HTTPS para consultar modelos.'}, status=403)
    if proveedor not in PROVEEDORES:
        return JsonResponse({'error': 'Proveedor no válido.'}, status=400)
    if request.POST.get('usar_actual') == '1':
        # La carga automática nunca envía una clave que el usuario esté escribiendo.
        datos = {proveedor + '-api_key': '', proveedor + '-base_url': valor(proveedor, 'base_url')}
    else:
        datos = request.POST
    formulario = ConsultaModelosForm(datos, proveedor=proveedor, prefix=proveedor)
    if not formulario.is_valid():
        return JsonResponse({'error': 'Revisa el formato de la clave y la URL de Model Studio.'}, status=400)
    configuracion = formulario.cleaned_data
    clave = configuracion['api_key'] or valor(proveedor, 'api_key')
    endpoint = configuracion.get('base_url', '')
    if proveedor == 'qwen' and not configuracion['api_key'] and endpoint != valor('qwen', 'base_url').rstrip('/'):
        # No enviar la clave compartida/personal guardada a un workspace diferente.
        return JsonResponse({'error': 'Introduce la clave de esa conexión para consultar un endpoint diferente.'}, status=400)
    try:
        return JsonResponse(listar_modelos(proveedor, api_key=clave, base_url=endpoint))
    except ErrorIA as error:
        return JsonResponse({'error': str(error)}, status=502)
    except Exception:
        return JsonResponse({'error': 'No se pudo consultar el catálogo. Se conserva tu selección.'}, status=502)
