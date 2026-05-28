/* AFJ CORE — Service Worker v1 */
const CACHE_NAME = "afj-core-v1";
const STATIC_ASSETS = [
  "/",
  "/login",
  "/fonts/Optima.ttc",
  "/logo-afj.svg",
  "/manifest.json",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_ASSETS)).catch(() => {})
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
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
    url.pathname.endsWith(".ttc") ||
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

  // Network-first for everything else (pages, JS chunks)
  event.respondWith(
    fetch(event.request).catch(() => caches.match(event.request))
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
