from django.test import SimpleTestCase, RequestFactory, override_settings
from .proxy import OrigenWorkerMiddleware


class ProxyTests(SimpleTestCase):
    @override_settings(ORIGIN_REQUIRE_WORKER=True,ORIGIN_SHARED_SECRET='synthetic-very-long-shared-secret')
    def test_origen_rechaza_acceso_directo_y_cabeceras_falsas(self):
        from django.http import HttpResponse
        m=OrigenWorkerMiddleware(lambda request:HttpResponse('ok'))
        r=RequestFactory().get('/',HTTP_X_FORWARDED_HOST='public.workers.dev',HTTP_X_FORWARDED_PROTO='https')
        self.assertEqual(m(r).status_code,403)
        r=RequestFactory().get('/',HTTP_X_EDUGESTOR_ORIGIN='synthetic-very-long-shared-secret')
        self.assertEqual(m(r).status_code,200)
