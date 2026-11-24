// 투자분석기 서비스 워커: 앱 셸 캐시만 한다 (크롬 '앱 설치' 조건 + 연결이 끊겼을 때 첫 화면).
// - 화면 이동(HTML): 네트워크 우선 → 연결이 안 되거나 서버 오류(5xx)면 캐시해 둔 첫 화면. 새 버전 배포는 다음 접속에 바로 반영된다
// - /assets/*(빌드 해시 파일 이름)·/icons/*: 캐시 우선
// - 그 밖(/api, 다른 출처)은 건드리지 않는다 — 시세·분석 값은 항상 서버에서 새로 받는다
// 없앨 때는 이 파일을 지우지 말고 '등록 해제 + 캐시 삭제'만 하는 sw.js를 같은 주소에 배포해야 한다
const CACHE = "coin-shell-v1";
/** 배포가 쌓이며 남는 옛 빌드 파일은 이 개수만 남기고 오래된 것부터 지운다 */
const MAX_ASSETS = 80;

const isHtml = (res) => (res.headers.get("content-type") || "").startsWith("text/html");

// 설치 때 첫 화면과 그 화면이 바로 쓰는 빌드 파일(JS·CSS)을 함께 저장한다(첫 방문 직후 오프라인 대비)
self.addEventListener("install", (event) => {
  event.waitUntil(
    (async () => {
      const cache = await caches.open(CACHE);
      const res = await fetch("/", { cache: "no-cache" });
      if (!res.ok || !isHtml(res)) throw new Error("첫 화면을 받지 못함");
      const html = await res.clone().text();
      await cache.put("/", res);
      const assets = [...new Set(html.match(/\/assets\/[^"'\s)]+/g) || [])];
      await cache.addAll(["/icons/icon-192.png", ...assets]);
      await self.skipWaiting();
    })(),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

/** 응답을 캐시에 넣는 일을 이벤트 수명에 묶는다(실패해도 화면에는 영향 없음) */
const keep = (event, work) => event.waitUntil(work().catch(() => {}));

/** 옛 빌드 파일 정리: /assets/ 항목이 MAX_ASSETS를 넘으면 먼저 넣은 것부터 지운다 */
async function trimAssets(cache) {
  const keys = (await cache.keys()).filter((r) => new URL(r.url).pathname.startsWith("/assets/"));
  await Promise.all(keys.slice(0, Math.max(0, keys.length - MAX_ASSETS)).map((r) => cache.delete(r)));
}

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  const path = url.pathname;

  if (req.mode === "navigate") {
    // API는 브라우저가 그대로 처리한다
    if (path.startsWith("/api/")) return;
    event.respondWith(
      (async () => {
        try {
          const res = await fetch(req);
          // 모든 화면 주소는 같은 index.html이므로 HTML 응답만 '/' 하나로 저장한다(manifest·이미지 등을 직접 열면 저장하지 않음)
          if (res.ok && isHtml(res)) {
            const copy = res.clone();
            keep(event, async () => (await caches.open(CACHE)).put("/", copy));
          }
          if (res.status >= 500) return (await caches.match("/")) || res;
          return res;
        } catch {
          return (await caches.match("/")) || Response.error();
        }
      })(),
    );
    return;
  }

  if (path.startsWith("/assets/") || path.startsWith("/icons/")) {
    event.respondWith(
      caches.match(req).then(
        (hit) =>
          hit ||
          fetch(req).then((res) => {
            if (res.ok) {
              const copy = res.clone();
              keep(event, async () => {
                const cache = await caches.open(CACHE);
                await cache.put(req, copy);
                await trimAssets(cache);
              });
            }
            return res;
          }),
      ),
    );
  }
});
