const CACHE_NAME = "bayan-bank-pwa-v1";

const OFFLINE_URL = "/offline/";

// Only this generic page is allowed in the cache.
const PRECACHE_URLS = [
    OFFLINE_URL
];


/*
|--------------------------------------------------------------------------
| Install
|--------------------------------------------------------------------------
*/

self.addEventListener("install", (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then((cache) => cache.addAll(PRECACHE_URLS))
            .then(() => self.skipWaiting())
    );
});


/*
|--------------------------------------------------------------------------
| Activate
|--------------------------------------------------------------------------
*/

self.addEventListener("activate", (event) => {
    event.waitUntil(
        caches.keys()
            .then((cacheNames) => {
                return Promise.all(
                    cacheNames
                        .filter((name) => name.startsWith("bayan-bank-pwa-"))
                        .filter((name) => name !== CACHE_NAME)
                        .map((name) => caches.delete(name))
                );
            })
            .then(() => self.clients.claim())
    );
});


/*
|--------------------------------------------------------------------------
| Fetch
|--------------------------------------------------------------------------
*/

self.addEventListener("fetch", (event) => {
    const request = event.request;
    const url = new URL(request.url);

    // Ignore requests to other origins.
    if (url.origin !== self.location.origin) {
        return;
    }

    // Only handle GET requests.
    if (request.method !== "GET") {
        return;
    }

    // Never intercept Django admin, authentication, or API requests.
    const protectedPaths = [
        "/admin/",
        "/login/",
        "/logout/",
        "/register/",
        "/api/",
        "/notifications/",
        "/chatbot/"
    ];

    if (
        protectedPaths.some((path) =>
            url.pathname.startsWith(path)
        )
    ) {
        return;
    }

    // Navigation requests must always go to the network.
    // If unavailable, show only the generic offline page.
    if (request.mode === "navigate") {
        event.respondWith(
            fetch(request).catch(async () => {
                const cache = await caches.open(CACHE_NAME);
                const offlinePage = await cache.match(OFFLINE_URL);

                if (offlinePage) {
                    return offlinePage;
                }

                return new Response(
                    "You are offline. Please reconnect and try again.",
                    {
                        status: 503,
                        headers: {
                            "Content-Type": "text/plain; charset=utf-8"
                        }
                    }
                );
            })
        );

        return;
    }

    // All other requests use the network.
    // No dynamic caching is performed.
    event.respondWith(
        fetch(request)
    );
});