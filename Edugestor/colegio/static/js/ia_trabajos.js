(() => {
  const panel = document.querySelector('[data-trabajo]');
  if (!panel) return;
  let timer, terminal = false, etapaAnterior = panel.dataset.etapa;
  async function consultar() {
    clearTimeout(timer);
    try {
      const respuesta = await fetch(panel.dataset.trabajo, {credentials: 'same-origin', cache: 'no-store'});
      if ([401, 403, 404].includes(respuesta.status) || respuesta.redirected) {
        document.getElementById('trabajo-conexion').textContent = 'Vuelve a iniciar sesión para recuperar la operación.';
        return;
      }
      if (!respuesta.ok) throw new Error('estado');
      const datos = await respuesta.json();
      panel.dataset.etapa = datos.etapa;
      const etiqueta = document.getElementById('trabajo-etapa');
      const etapas = {pendiente: 'Pendiente', preparando: 'Preparando', generando: 'Generando', validando: 'Validando', completado: 'Completado', error: 'Error'};
      if (etiqueta) etiqueta.textContent = etapas[datos.etapa] || datos.etapa;
      document.getElementById('trabajo-mensaje').textContent = datos.mensaje;
      document.getElementById('trabajo-duracion').textContent = datos.duracion;
      document.getElementById('trabajo-conexion').textContent = '';
      panel.querySelectorAll('[data-etapa]').forEach(li => li.setAttribute('aria-current', String(li.dataset.etapa === datos.etapa)));
      const lista = document.getElementById('trabajo-actividad');
      lista.replaceChildren(...datos.actividad.slice(-5).map(item => {
        const li = document.createElement('li'); li.textContent = item.mensaje; return li;
      }));
      const enlace = document.getElementById('trabajo-resultado');
      enlace.hidden = !datos.resultado_url;
      if (datos.resultado_url) enlace.href = datos.resultado_url;
      terminal = ['completado', 'error'].includes(datos.etapa);
      const reintentar = document.getElementById('trabajo-reintentar');
      if (reintentar) reintentar.hidden = datos.etapa !== 'error';
      if (datos.etapa === 'completado' && etapaAnterior !== 'completado' && !datos.resultado_url) location.reload();
      etapaAnterior = datos.etapa;
    } catch (_) {
      document.getElementById('trabajo-conexion').textContent = 'Conexión interrumpida. Consultaremos nuevamente; no se reenviará la operación.';
    }
    if (!terminal) timer = setTimeout(consultar, document.hidden ? 15000 : 2000);
  }
  document.addEventListener('visibilitychange', () => { if (!terminal) consultar(); });
  consultar();
})();
