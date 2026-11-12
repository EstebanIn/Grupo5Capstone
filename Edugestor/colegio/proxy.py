from django.conf import settings
from django.http import HttpResponseForbidden
from django.utils.crypto import constant_time_compare


class OrigenWorkerMiddleware:
    """Verifica el salto de confianza antes de interpretar cabeceras de proxy."""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if getattr(settings, 'ORIGIN_REQUIRE_WORKER', False):
            secreto = getattr(settings, 'ORIGIN_SHARED_SECRET', '')
            if not secreto or not constant_time_compare(request.headers.get('X-Edugestor-Origin', ''), secreto):
                return HttpResponseForbidden('Origen no autorizado.')
        return self.get_response(request)
