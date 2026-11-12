export default {
  async fetch(request, env) {
    const incoming = new URL(request.url), origin = new URL(env.ORIGIN_URL);
    if (incoming.hostname !== env.PUBLIC_HOST || origin.protocol !== 'https:' || !env.ORIGIN_SHARED_SECRET) {
      return new Response('Configuración no disponible', { status: 503 });
    }
    const target = new URL(origin);
    target.pathname = incoming.pathname;
    target.search = incoming.search;
    const headers = new Headers(request.headers);
    for (const name of [...headers.keys()]) {
      if (name.startsWith('x-forwarded-') || name === 'forwarded' || name === 'x-edugestor-origin') headers.delete(name);
    }
    headers.set('Host', origin.host);
    headers.set('X-Forwarded-Host', env.PUBLIC_HOST);
    headers.set('X-Forwarded-Proto', 'https');
    headers.set('X-Edugestor-Origin', env.ORIGIN_SHARED_SECRET);
    let upstream;
    try {
      upstream = await fetch(target, { method: request.method, headers,
        body: ['GET','HEAD'].includes(request.method) ? undefined : request.body,
        redirect: 'manual', cf: { cacheTtl: 0, cacheEverything: false } });
    } catch (_) {
      return new Response('El servidor está temporalmente fuera de servicio. Vuelve a intentar.', {
        status: 502, headers: {'Cache-Control': 'no-store'} });
    }
    const response = new Response(upstream.body, upstream);
    response.headers.set('Cache-Control', 'private, no-store');
    response.headers.delete('X-Edugestor-Origin');
    const location = response.headers.get('Location');
    if (location) {
      const redirect = new URL(location, target);
      if (redirect.origin === origin.origin) {
        redirect.protocol = incoming.protocol; redirect.host = incoming.host;
        response.headers.set('Location', redirect.href);
      }
    }
    return response;
  }
};
