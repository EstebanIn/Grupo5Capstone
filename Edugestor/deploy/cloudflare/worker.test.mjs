import test from 'node:test';
import assert from 'node:assert/strict';
import worker from './worker.mjs';
const env = {ORIGIN_URL:'https://origen.duckdns.org',PUBLIC_HOST:'demo.ejemplo.workers.dev',ORIGIN_SHARED_SECRET:'synthetic-shared-secret'};

test('reemplaza cabeceras no confiables y transmite POST sin modificarlo', async () => {
  const original=globalThis.fetch;
  globalThis.fetch=async(url,opts)=>{
    assert.equal(url.hostname,'origen.duckdns.org');assert.equal(url.search,'?pagina=2');
    assert.equal(opts.headers.get('X-Forwarded-Host'),env.PUBLIC_HOST);
    assert.equal(opts.headers.get('X-Forwarded-Proto'),'https');
    assert.equal(opts.headers.get('Forwarded'),null);
    assert.equal(opts.headers.get('X-Edugestor-Origin'),env.ORIGIN_SHARED_SECRET);
    assert.equal(await new Response(opts.body).text(),'datos=á&csrfmiddlewaretoken=qa');
    assert.equal(opts.redirect,'manual');
    return new Response('archivo original',{headers:{'Content-Type':'application/pdf','Set-Cookie':'sessionid=qa; Secure; HttpOnly'}});
  };
  try {
    const respuesta=await worker.fetch(new Request('https://'+env.PUBLIC_HOST+'/exportar/?pagina=2',{
      method:'POST',body:'datos=á&csrfmiddlewaretoken=qa',headers:{'X-Forwarded-Host':'evil.test',Forwarded:'host=evil.test','X-Edugestor-Origin':'evil'}}),env);
    assert.equal(await respuesta.text(),'archivo original');assert.match(respuesta.headers.get('Cache-Control'),/no-store/);
    assert.match(respuesta.headers.get('Set-Cookie'),/HttpOnly/);
  } finally {globalThis.fetch=original;}
});

test('una ruta con doble slash conserva el origen autorizado',async()=>{
  const original=globalThis.fetch;
  globalThis.fetch=async(url)=>{assert.equal(url.origin,env.ORIGIN_URL);return new Response('ok');};
  try{await worker.fetch(new Request('https://'+env.PUBLIC_HOST+'//evil.test/path'),env);}finally{globalThis.fetch=original;}
});

test('reescribe redirección del origen hacia la dirección pública',async()=>{
  const original=globalThis.fetch;
  globalThis.fetch=async()=>new Response(null,{status:302,headers:{Location:env.ORIGIN_URL+'/login/?next=%2Fpanel%2F'}});
  try{const r=await worker.fetch(new Request('https://'+env.PUBLIC_HOST+'/panel/'),env);assert.equal(r.headers.get('Location'),'https://'+env.PUBLIC_HOST+'/login/?next=%2Fpanel%2F');}finally{globalThis.fetch=original;}
});

test('rechaza host ajeno y comunica caída sin filtrar excepción',async()=>{
  assert.equal((await worker.fetch(new Request('https://evil.test/'),env)).status,503);
  const original=globalThis.fetch;globalThis.fetch=async()=>{throw new Error('PRIVATE SECRET');};
  try{const r=await worker.fetch(new Request('https://'+env.PUBLIC_HOST),env);assert.equal(r.status,502);assert.doesNotMatch(await r.text(),/PRIVATE/);}finally{globalThis.fetch=original;}
});
