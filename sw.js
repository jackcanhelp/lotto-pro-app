// 智能彩券選號系統 Pro - Service Worker
// 迭代8: 離線支援與快取策略

const CACHE_NAME = 'lotto-pro-v1';
const ASSETS_TO_CACHE = [
  '/',
  '/index.html',
  '/manifest.json'
];

// 安裝事件 - 預快取核心資源
self.addEventListener('install', (event) => {
  console.log('[SW] 安裝中...');
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => {
        console.log('[SW] 快取核心資源');
        return cache.addAll(ASSETS_TO_CACHE);
      })
      .then(() => {
        console.log('[SW] 安裝完成');
        return self.skipWaiting();
      })
      .catch((err) => {
        console.error('[SW] 快取失敗:', err);
      })
  );
});

// 啟動事件 - 清理舊快取
self.addEventListener('activate', (event) => {
  console.log('[SW] 啟動中...');
  event.waitUntil(
    caches.keys()
      .then((cacheNames) => {
        return Promise.all(
          cacheNames
            .filter((name) => name !== CACHE_NAME)
            .map((name) => {
              console.log('[SW] 刪除舊快取:', name);
              return caches.delete(name);
            })
        );
      })
      .then(() => {
        console.log('[SW] 啟動完成');
        return self.clients.claim();
      })
  );
});

// 攔截請求 - 快取優先策略
self.addEventListener('fetch', (event) => {
  // 只處理 GET 請求
  if (event.request.method !== 'GET') {
    return;
  }

  // 跳過非同源請求
  if (!event.request.url.startsWith(self.location.origin)) {
    return;
  }

  event.respondWith(
    caches.match(event.request)
      .then((cachedResponse) => {
        if (cachedResponse) {
          // 快取命中，返回快取並在背景更新
          console.log('[SW] 快取命中:', event.request.url);

          // 背景更新快取 (Stale-While-Revalidate)
          const fetchPromise = fetch(event.request)
            .then((networkResponse) => {
              if (networkResponse && networkResponse.status === 200) {
                const responseClone = networkResponse.clone();
                caches.open(CACHE_NAME)
                  .then((cache) => {
                    cache.put(event.request, responseClone);
                  });
              }
              return networkResponse;
            })
            .catch(() => {
              // 網路失敗，忽略
            });

          return cachedResponse;
        }

        // 快取未命中，嘗試網路請求
        console.log('[SW] 網路請求:', event.request.url);
        return fetch(event.request)
          .then((networkResponse) => {
            // 快取成功的回應
            if (networkResponse && networkResponse.status === 200) {
              const responseClone = networkResponse.clone();
              caches.open(CACHE_NAME)
                .then((cache) => {
                  cache.put(event.request, responseClone);
                });
            }
            return networkResponse;
          })
          .catch(() => {
            // 網路失敗，返回離線頁面（如果是導航請求）
            if (event.request.mode === 'navigate') {
              return caches.match('/index.html');
            }
            return new Response('離線中', {
              status: 503,
              statusText: 'Service Unavailable'
            });
          });
      })
  );
});

// 背景同步（未來擴展用）
self.addEventListener('sync', (event) => {
  console.log('[SW] 背景同步:', event.tag);
});

// 推播通知（未來擴展用）
self.addEventListener('push', (event) => {
  console.log('[SW] 推播通知:', event.data?.text());
});
