const CACHE = "expense-tracker-v4";

self.addEventListener("install", (event) => {
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    Promise.all([
      caches.keys().then((keys) =>
        Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
      ),
      self.clients.claim(),
    ])
  );
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Never cache API calls — always go to network
  if (url.pathname.startsWith("/api/")) return;

  // Never cache JS files — ensures fresh script.js (fixes stale-code bugs on iOS)
  if (url.pathname.endsWith(".js")) return;

  // Static assets (CSS, images, fonts): cache-first
  if (/\.(css|png|svg|ico|woff2?)$/.test(url.pathname)) {
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
  if (request.method !== "GET") return fetch(request);
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
    if (response.ok && request.method === "GET" && !request.url.includes("/api/")) {
      const cache = await caches.open(CACHE);
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    if (request.method !== "GET") throw new Error("Offline");
    const cached = await caches.match(request);
    if (cached) return cached;
    if (request.mode === "navigate") {
      return caches.match("/");
    }
    return new Response("Offline", { status: 503 });
  }
}
