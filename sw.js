const CACHE = 'keiba-lab-static-v3.8.0';
const APP_SHELL = ['./', './index.html', './manifest.webmanifest', './icons/icon-192.png', './icons/icon-512.png', './icons/apple-touch-icon.png'];
self.addEventListener('install', event => { event.waitUntil(caches.open(CACHE).then(cache=>cache.addAll(APP_SHELL)).then(()=>self.skipWaiting())); });
self.addEventListener('activate', event => { event.waitUntil(caches.keys().then(names=>Promise.all(names.filter(n=>n.startsWith('keiba-lab-static-')&&n!==CACHE).map(n=>caches.delete(n)))).then(()=>self.clients.claim())); });
self.addEventListener('fetch', event => {
 const req=event.request;
 if(req.method!=='GET')return;
 const u=new URL(req.url);
 if(u.origin!==self.location.origin || !u.pathname.startsWith(new URL(self.registration.scope).pathname))return;
 if(req.mode==='navigate'){
  event.respondWith(fetch(req).then(resp=>{if(resp.ok){const copy=resp.clone();event.waitUntil(caches.open(CACHE).then(cache=>cache.put('./index.html',copy)));}return resp;}).catch(()=>caches.match('./index.html')));
 }else if(['/manifest.webmanifest','/icons/icon-192.png','/icons/icon-512.png','/icons/apple-touch-icon.png'].some(path=>u.pathname.endsWith(path))){
  event.respondWith(caches.match(req).then(cached=>cached||fetch(req)));
 }
});