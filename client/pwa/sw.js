// 修复的 client/pwa/sw.js
const CACHE_NAME = 'nas-pwa-v1.0.1';  // 更新版本号
const API_CACHE_NAME = 'nas-api-cache-v1.0.1';

// 修复：移除外部CDN资源，避免CORS问题
const STATIC_CACHE_URLS = [
  '/',
  '/static/app.js',
  '/static/index.html',
  '/static/pwa/manifest.json',
  '/static/pwa/icons/icon-192.png',
  '/static/pwa/icons/icon-512.png'
  // 移除外部CDN，因为它们有CORS限制：
  // 'https://cdn.tailwindcss.com',
  // 'https://unpkg.com/vue@3/dist/vue.global.prod.js',
  // 'https://cdn.jsdelivr.net/npm/axios/dist/axios.min.js'
];

const CACHEABLE_APIS = [
  '/api/system',
  '/api/disk',
  '/api/drives'
];

// 安装事件：缓存静态资源
self.addEventListener('install', (event) => {
  console.log('[SW] 安装中...');

  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(async (cache) => {
        console.log('[SW] 缓存静态资源');

        // 逐个缓存，避免因为单个失败导致整体失败
        const cachePromises = STATIC_CACHE_URLS.map(async (url) => {
          try {
            await cache.add(url);
            console.log(`[SW] 缓存成功: ${url}`);
          } catch (error) {
            console.warn(`[SW] 缓存失败: ${url}`, error);
          }
        });

        await Promise.allSettled(cachePromises);
        console.log('[SW] 静态资源缓存完成');
      })
      .then(() => {
        console.log('[SW] 安装完成');
        return self.skipWaiting();
      })
      .catch((error) => {
        console.error('[SW] 安装失败:', error);
        // 即使缓存失败也继续安装，只是没有离线功能
        return self.skipWaiting();
      })
  );
});

// 激活事件：清理旧缓存
self.addEventListener('activate', (event) => {
  console.log('[SW] 激活中...');

  event.waitUntil(
    caches.keys()
      .then((cacheNames) => {
        return Promise.all(
          cacheNames.map((cacheName) => {
            if (cacheName !== CACHE_NAME && cacheName !== API_CACHE_NAME) {
              console.log('[SW] 删除旧缓存:', cacheName);
              return caches.delete(cacheName);
            }
          })
        );
      })
      .then(() => {
        console.log('[SW] 激活完成');
        return self.clients.claim();
      })
  );
});

// 拦截网络请求
self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // 只处理同源请求，忽略外部CDN
  if (url.origin !== location.origin) {
    return; // 让外部请求正常通过，不拦截
  }

  // API请求处理
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(handleApiRequest(request));
    return;
  }

  // 静态资源请求处理
  event.respondWith(handleStaticRequest(request));
});

// 处理API请求（网络优先，缓存降级）
async function handleApiRequest(request) {
  const url = new URL(request.url);

  try {
    const networkResponse = await fetch(request);

    if (networkResponse.ok && CACHEABLE_APIS.some(api => url.pathname.startsWith(api))) {
      const cache = await caches.open(API_CACHE_NAME);
      if (request.method === 'GET') {
        cache.put(request, networkResponse.clone());
      }
    }

    return networkResponse;
  } catch (error) {
    console.log('[SW] 网络请求失败，尝试缓存:', request.url);

    const cachedResponse = await caches.match(request);
    if (cachedResponse) {
      return cachedResponse;
    }

    if (url.pathname === '/api/system') {
      return new Response(JSON.stringify({
        hostname: '离线模式',
        os: '离线模式',
        cpu_percent: 0,
        memory_total: 0,
        memory_used: 0,
        uptime: 0
      }), {
        headers: { 'Content-Type': 'application/json' }
      });
    }

    return new Response(JSON.stringify({
      error: '网络连接失败，请检查网络连接'
    }), {
      status: 503,
      headers: { 'Content-Type': 'application/json' }
    });
  }
}

// 处理静态资源请求（缓存优先，网络降级）
async function handleStaticRequest(request) {
  const cachedResponse = await caches.match(request);
  if (cachedResponse) {
    return cachedResponse;
  }

  try {
    const networkResponse = await fetch(request);

    if (networkResponse.ok) {
      const cache = await caches.open(CACHE_NAME);
      cache.put(request, networkResponse.clone());
    }

    return networkResponse;
  } catch (error) {
    console.log('[SW] 静态资源请求失败:', request.url);

    if (request.headers.get('Accept')?.includes('text/html')) {
      return new Response(`
        <!DOCTYPE html>
        <html>
        <head>
          <meta charset="UTF-8">
          <title>离线模式 - NAS</title>
          <meta name="viewport" content="width=device-width, initial-scale=1.0">
          <style>
            body { font-family: Arial, sans-serif; text-align: center; padding: 50px; background: #f7fafc; }
            .offline-msg { max-width: 400px; margin: 0 auto; background: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
            .retry-btn { background: #3498db; color: white; padding: 10px 20px; border: none; border-radius: 5px; cursor: pointer; margin-top: 20px; }
            .icon { font-size: 48px; margin-bottom: 20px; }
          </style>
        </head>
        <body>
          <div class="offline-msg">
            <div class="icon">📡</div>
            <h1>离线模式</h1>
            <p>当前网络连接不可用，请检查网络连接后重试。</p>
            <button class="retry-btn" onclick="window.location.reload()">重新连接</button>
          </div>
        </body>
        </html>
      `, {
        headers: { 'Content-Type': 'text/html' }
      });
    }

    return new Response('资源不可用', { status: 503 });
  }
}

// 监听消息事件
self.addEventListener('message', (event) => {
  if (event.data && event.data.type) {
    switch (event.data.type) {
      case 'SKIP_WAITING':
        self.skipWaiting();
        break;
      case 'CLEAR_CACHE':
        clearAllCaches();
        break;
    }
  }
});

// 清理所有缓存
async function clearAllCaches() {
  const cacheNames = await caches.keys();
  await Promise.all(
    cacheNames.map(cacheName => caches.delete(cacheName))
  );
  console.log('[SW] 所有缓存已清理');
}