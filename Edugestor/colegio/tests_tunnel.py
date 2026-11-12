"""Arranque seguro del perfil remoto sin base, claves reales ni servicios externos."""
import json
import os
import subprocess
import sys
from django.conf import settings
from django.test import SimpleTestCase


class TunnelSettingsTests(SimpleTestCase):
    def cargar(self, **cambios):
        env={**os.environ,'DJANGO_SECRET_KEY':'test-only-tunnel-key-never-used-on-a-server-'*2,
            'TUNEL_PUBLIC_HOST':'prueba.trycloudflare.com','IA_PROVEEDOR':'qwen',**cambios}
        return subprocess.run([sys.executable,'-c',
            'import json;from config import tunnel as s;print(json.dumps({"debug":s.DEBUG,"secure":s.SESSION_COOKIE_SECURE and s.CSRF_COOKIE_SECURE,"host":s.PUBLIC_HOST,"hosts":s.ALLOWED_HOSTS,"csrf":s.CSRF_TRUSTED_ORIGINS,"proxy":s.SECURE_PROXY_SSL_HEADER,"cache":"config.tunnel.SinCachePrivada" in s.MIDDLEWARE}))'],
            cwd=settings.BASE_DIR,env=env,capture_output=True,text=True,timeout=20)

    def test_perfil_https_y_host_exacto(self):
        p=self.cargar();self.assertEqual(p.returncode,0,p.stderr)
        d=json.loads(p.stdout);self.assertFalse(d['debug']);self.assertTrue(d['secure']);self.assertTrue(d['cache'])
        self.assertIn(d['host'],d['hosts']);self.assertNotIn('*',d['hosts'])
        self.assertEqual(d['csrf'],['https://prueba.trycloudflare.com'])
        self.assertEqual(d['proxy'],['HTTP_X_FORWARDED_PROTO','https'])

    def test_rechaza_host_clave_debil_y_simulacion(self):
        for cambios in [{'TUNEL_PUBLIC_HOST':'prueba.trycloudflare.com/otro'},
                        {'TUNEL_PUBLIC_HOST':'malicioso.example'},
                        {'DJANGO_SECRET_KEY':'corta'},{'IA_PROVEEDOR':'simulado'}]:
            with self.subTest(cambios=cambios):self.assertNotEqual(self.cargar(**cambios).returncode,0)
