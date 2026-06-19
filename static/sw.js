const CACHE = "expense-tracker-v3";
const STATIC_ASSETS = [
  "/",
  "/static/style.css",
  "/static/script.js",
  "/static/manifest.json",
  "/static/icon-192.png",
  "/static/icon-512.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(STATIC_ASSETS))
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // API calls: network-first
  if (url.pathname.startsWith("/api/")) {
    event.respondWith(networkFirst(request));
    return;
  }

  // Static assets: cache-first
  if (
    STATIC_ASSETS.includes(url.pathname) ||
    /\.(css|js|png|svg|ico|woff2?)$/.test(url.pathname)
  ) {
    event.respondWith(cacheFirst(request));
    return;
  }

  // Navigation & all else: network-first
  event.respondWith(networkFirst(request));
});

self.addEventListener("push", (event) => {
  let data = { title: "Expense Tracker", body: "", icon: "/static/icon-192.png" };
  try {
    const payload = event.data ? JSON.parse(event.data.text()) : {};
    data = { ...data, ...payload };
  } catch {}

  event.waitUntil(
    self.registration.showNotification(data.title, {
      body: data.body,
      icon: data.icon,
      badge: data.badge || data.icon,
      tag: data.tag || "default",
      data: data.data || {},
      vibrate: [200, 100, 200],
      requireInteraction: data.tag === "budget-alert",
    })
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const urlToOpen = new URL("/", self.location.origin);
  const ntype = event.notification.data?.type;
  if (ntype === "budget") {
    urlToOpen.pathname = "/budgets";
  } else if (ntype === "recurring") {
    urlToOpen.pathname = "/recurring";
  }
  event.waitUntil(
    clients.matchAll({ type: "window", includeUncontrolled: true }).then((windowClients) => {
      for (const client of windowClients) {
        if (client.url === urlToOpen.href && "focus" in client) return client.focus();
      }
      return clients.openWindow(urlToOpen.href);
    })
  );
});

async function cacheFirst(request) {
  const cached = await caches.match(request);
  if (cached) return cached;
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(CACHE);
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    return new Response("Offline", { status: 503 });
  }
}

async function networkFirst(request) {
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(CACHE);
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    const cached = await caches.match(request);
    if (cached) return cached;
    if (request.mode === "navigate") {
      return caches.match("/");
    }
    return new Response("Offline", { status: 503 });
  }
}
