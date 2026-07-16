/* AFJ CORE — Service Worker v2
   v1 pré-cacheava /fonts/Optima.ttc (inexistente): cache.addAll é atômico,
   então NENHUM asset era cacheado e o offline nunca funcionou. v2 usa adds
   tolerantes a falha, assets reais e fallback offline.html para navegação. */
const CACHE_NAME = "afj-core-v2";
const OFFLINE_URL = "/offline.html";
const STATIC_ASSETS = [
  "/",
  "/login",
  OFFLINE_URL,
  "/logo-afj.svg",
  "/logo-afj-mark.png",
  "/manifest.json",
  "/icons/icon-192.png",
  "/icons/icon-512.png",
  "/fonts/Optima-Regular.woff2",
  "/fonts/Optima-Bold.woff2",
  "/fonts/Optima-Italic.woff2",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) =>
      // Tolerante a falha: um 404 não derruba o precache inteiro (addAll é atômico).
      Promise.allSettled(STATIC_ASSETS.map((asset) => cache.add(asset)))
    )
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    ).then(() =>
      // Avisa as janelas abertas que há versão nova (o provider mostra o aviso).
      self.clients.matchAll({ type: "window" }).then((clients) =>
        clients.forEach((c) => c.postMessage({ type: "SW_UPDATED" }))
      )
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);

  // Never cache API calls, WebSocket, or auth routes
  if (
    url.pathname.startsWith("/api/") ||
    url.pathname.startsWith("/api/v1/ws") ||
    event.request.method !== "GET"
  ) {
    return;
  }

  // Cache-first for static assets (fonts, images, icons)
  if (
    url.pathname.startsWith("/fonts/") ||
    url.pathname.startsWith("/icons/") ||
    url.pathname.endsWith(".woff2") ||
    url.pathname.endsWith(".svg") ||
    url.pathname.endsWith(".png")
  ) {
    event.respondWith(
      caches.match(event.request).then((cached) => {
        return cached || fetch(event.request).then((res) => {
          const clone = res.clone();
          caches.open(CACHE_NAME).then((c) => c.put(event.request, clone));
          return res;
        });
      })
    );
    return;
  }

  // Network-first para páginas/chunks; offline: cache → shell offline.html
  event.respondWith(
    fetch(event.request).catch(async () => {
      const cached = await caches.match(event.request);
      if (cached) return cached;
      if (event.request.mode === "navigate") {
        const offline = await caches.match(OFFLINE_URL);
        if (offline) return offline;
      }
      return Response.error();
    })
  );
});

/* ─── Web Push ────────────────────────────────────────────────────────────── */
self.addEventListener("push", (event) => {
  let data = { title: "AFJ CORE", body: "Nova notificação", url: "/dashboard", icon: "/icons/icon-192.png" };
  try { Object.assign(data, JSON.parse(event.data ? event.data.text() : "{}")); } catch {}

  event.waitUntil(
    self.registration.showNotification(data.title, {
      body: data.body,
      icon: data.icon,
      badge: "/icons/icon-192.png",
      tag: "afj-push",
      renotify: true,
      requireInteraction: false,
      data: { url: data.url },
    })
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const targetUrl = (event.notification.data && event.notification.data.url) || "/dashboard";

  event.waitUntil(
    clients.matchAll({ type: "window", includeUncontrolled: true }).then((windowClients) => {
      // Focus existing window if available and navigate
      const existing = windowClients.find((c) => "focus" in c);
      if (existing) {
        return existing.focus().then((w) => {
          if (w.navigate) w.navigate(targetUrl);
          return w;
        });
      }
      // Otherwise open a new window
      return clients.openWindow(targetUrl);
    })
  );
});
