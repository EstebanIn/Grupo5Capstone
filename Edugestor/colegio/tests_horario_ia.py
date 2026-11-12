"""Presentación chilena de fechas; los instantes originales permanecen en UTC."""
import uuid
from datetime import datetime, timezone as utc
from django.urls import reverse
from .tests import AsistenteIATestBase
from .models import RegistroIA, TrabajoIA, InstrumentoIA


class HorarioIATests(AsistenteIATestBase):
    def setUp(self):
        super().setUp();self.client.force_login(self.usuario_docente)

    def test_registro_usa_hora_estacional_y_fecha_local_sin_alterar_el_instante(self):
        r=RegistroIA.objects.create(usuario=self.usuario_docente,proveedor='qwen',operacion='Horario',estado='OK')
        casos=[(datetime(2026,11,12,14,30,tzinfo=utc.utc),'12/11/2026 11:30'),
               (datetime(2026,7,12,14,30,tzinfo=utc.utc),'12/07/2026 10:30'),
               (datetime(2026,11,13,2,30,tzinfo=utc.utc),'12/11/2026 23:30')]
        for instante,esperado in casos:
            with self.subTest(instante=instante):
                RegistroIA.objects.filter(pk=r.pk).update(fecha=instante)
                pagina=self.client.get(reverse('registro_ia'))
                self.assertContains(pagina,'Fecha y hora (Chile)');self.assertContains(pagina,esperado)
                self.assertNotContains(pagina,'Fecha (UTC)')
                r.refresh_from_db();self.assertEqual(r.fecha,instante)

    def test_operaciones_recientes_muestran_el_mismo_horario(self):
        t=TrabajoIA.objects.create(usuario=self.usuario_docente,sesion='horario',idempotencia=uuid.uuid4(),
            huella='a'*64,conexion_huella='b'*64,operacion='material',proveedor='qwen',modelo='qwen3.8-flash',estado='completado')
        instante=datetime(2026,11,12,14,30,tzinfo=utc.utc)
        TrabajoIA.objects.filter(pk=t.pk).update(creado=instante)
        self.assertContains(self.client.get(reverse('ia_operaciones')),'12/11/2026 11:30')
        t.refresh_from_db();self.assertEqual(t.creado,instante)

    def test_documentos_respetan_el_dia_local_en_el_limite_de_medianoche(self):
        i=InstrumentoIA.objects.create(docente=self.docente,carga=self.carga,tipo='MATERIAL',titulo='Fecha local',
            contenido={'contenido':'Ejemplo'},contenido_ia={'contenido':'Ejemplo'})
        instante=datetime(2026,11,13,2,30,tzinfo=utc.utc)
        InstrumentoIA.objects.filter(pk=i.pk).update(fecha_creacion=instante)
        self.assertContains(self.client.get(reverse('ia_documentos')),'12/11/2026')
        i.refresh_from_db();self.assertEqual(i.fecha_creacion,instante)
