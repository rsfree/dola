#!/usr/bin/env node
/**
 * dola-signer —— a_bogus 铸签 sidecar（生产标准）。
 *
 * 原理（docs/upstream/dola-api.md §4.0.1）：
 *   1. headless Chrome 注入 cookie，加载 dola 页面 → mssdk SDK 补丁 window.fetch
 *   2. /sign 时页面内 fetch(目标URL) —— SDK 自动追加 msToken+a_bogus
 *   3. CDP 请求拦截抓到【签名后 URL】即 abort —— 网络层不真发，零副作用
 *
 * API：
 *   GET  /healthz -> {"ok":true,"page_ready":bool}
 *   POST /sign    {"url":"<未签名完整URL>","method":"POST","body":"<字符串>"}
 *              -> {"url":"<含 msToken+a_bogus 的签名URL>"}
 *
 * 环境变量：
 *   CHROME_PATH   Chrome 可执行文件路径（必填）
 *   DOLA_COOKIE   cookie 串（注入页面；a_bogus 本身不绑会话，但页面加载需要）
 *   PROXY         可选，Chrome 出站代理（写路径地理围栏时需要）
 *   PORT          默认 8491
 */
const http = require("http");
const puppeteer = require("puppeteer-extra");
const StealthPlugin = require("puppeteer-extra-plugin-stealth");
puppeteer.use(StealthPlugin());

const PORT = parseInt(process.env.PORT || "8491", 10);

// 🔴 进程级异常钩子：boot 后静默退出排查（本地实测踩过）
process.on("unhandledRejection", (r) =>
  console.error("[dola-signer] unhandledRejection:", r));
process.on("uncaughtException", (e) =>
  console.error("[dola-signer] uncaughtException:", e));
process.on("exit", (code) => console.log(`[dola-signer] process exit code=${code}`));
const CHROME_PATH = process.env.CHROME_PATH || "";
const DOLA_COOKIE = process.env.DOLA_COOKIE || "";
const PROXY = process.env.PROXY || "";
const PAGE_URL = "https://www.dola.com/chat/create-image";
const MINT_TIMEOUT_MS = 20000;

let browser = null;
let page = null;
let pageReady = false;
let bootError = null;

function parseCookieString(str) {
  const out = [];
  for (const part of str.split(";")) {
    const i = part.indexOf("=");
    if (i < 0) continue;
    const name = part.slice(0, i).trim();
    const value = part.slice(i + 1).trim();
    if (!name) continue;
    out.push({ name, value, domain: ".dola.com", path: "/", secure: true });
  }
  return out;
}

async function boot() {
  if (!CHROME_PATH) throw new Error("CHROME_PATH 未配置");
  const args = [
    "--no-sandbox",
    "--disable-gpu",
    "--disable-dev-shm-usage",
    "--disable-software-rasterizer",
    "--disable-extensions",
    "--disable-popup-blocking",
    "--disable-notifications",
    "--disable-infobars",
    "--disable-blink-features=AutomationControlled",
    "--disable-features=IsolateOrigins,site-per-process",
    "--disable-site-isolation-trials",
    "--no-first-run",
    "--no-default-browser-check",
    "--window-size=1280,800",
  ];
  if (PROXY) args.push(`--proxy-server=${PROXY}`);
  browser = await puppeteer.launch({
    executablePath: CHROME_PATH,
    headless: "new",
    args,
  });
  page = await browser.newPage();
  // 反检测：覆写 navigator.webdriver
  await page.evaluateOnNewDocument(() => {
    Object.defineProperty(navigator, "webdriver", { get: () => undefined });
    // 覆写 chrome.runtime 防检测
    window.chrome = window.chrome || {};
    window.chrome.runtime = window.chrome.runtime || { connect: () => {} };
  });
  UA_USED = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 " +
      "(KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36";
  await page.setUserAgent(UA_USED);
  await page.setViewport({ width: 1280, height: 800 });
  if (DOLA_COOKIE) {
    const cookies = parseCookieString(DOLA_COOKIE);
    if (cookies.length) await page.setCookie(...cookies);
  }
  // 请求拦截：所有请求默认放行；mint 请求在捕获签名 URL 后 abort（不真发）
  await page.setRequestInterception(true);
  page.on("request", (req) => {
    const pending = pendingMints.find(
      (m) => !m.done && req.url().startsWith(m.urlPrefix)
    );
    if (pending) {
      pending.done = true;
      pending.signedUrl = req.url();
      try {
        req.abort("aborted");
      } catch (_) {}
      pending.resolve();
      return;
    }
    if (!req.isInterceptResolutionHandled()) req.continue();
  });
  await page.goto(PAGE_URL, { waitUntil: "domcontentloaded", timeout: 60000 });

    // 🔴 金丝雀等 hook：mssdk 初始化要数分钟，等真出 a_bogus 才置 ready（上限 8 分钟）
    const deadline = Date.now() + 8 * 60 * 1000;
    let canaryOk = false;
    while (Date.now() < deadline) {
      await new Promise((r) => setTimeout(r, 15000));
      try {
        await mintOnce("https://www.dola.com/chat/completion?aid=495671&bootcanary=1", "POST", "{}");
        canaryOk = true;
        break;
      } catch { /* 未就绪继续等 */ }
    }
    console.log(`[dola-signer] boot canary ${canaryOk ? "ok" : "TIMEOUT (8min)"}`);
  pageReady = true;
}

/** 单次铸签尝试。 */
// 🔴 hook 存活预检：mssdk 会话过期后 fetch hook 静默消失 ⇒ 铸签前先验，过期就重载
async function hookAlive() {
  try {
    return await page.evaluate(() =>
      !!(window.byted_acrawler && typeof window.fetch === "function" &&
         window.fetch.toString().length > 500)
    );
  } catch { return false; }
}

async function mintOnce(url, method, body) {
  const u = new URL(url);
  const urlPrefix = `${u.origin}${u.pathname}`;
  const pending = { urlPrefix, done: false, signedUrl: null, resolve: null };
  const p = new Promise((resolve, reject) => {
    pending.resolve = resolve;
    setTimeout(() => {
      if (!pending.done) {
        pending.done = true;
        reject(new Error("mint timeout：SDK 未在限时内发出签名请求"));
      }
    }, MINT_TIMEOUT_MS);
  });
  pendingMints.push(pending);
  // 不 await fetch 本体（会被我们 abort，注定 reject）；吞掉异常
  page.evaluate(
    async (u, m, b) => {
      try {
        await fetch(u, { method: m, body: b, credentials: "include" });
      } catch (_) {}
    },
    url,
    method,
    body
  ).catch(() => {});
  await p;
  if (pendingMints.includes(pending))
    pendingMints.splice(pendingMints.indexOf(pending), 1);
  const out = pending.signedUrl;
  // 🔴 会话过期时 fetch 未被 hook ⇒ 拦截器抓到裸 URL（无 a_bogus）。
  //    必须视为失败抛错，上层 mintSignedUrl 才会 reload 自愈。
  if (!out || !out.includes("a_bogus=")) {
    throw new Error("mint result missing a_bogus (mssdk session dead)");
  }
  return out;
}

/** 页面老化自愈：SDK 长时间不开口 ⇒ 刷新页面重新加载 mssdk。 */
async function reloadPage() {
  console.log("[dola-signer] page stale -> reloading");
  pageReady = false;
  try {
    await page.goto(PAGE_URL, { waitUntil: "domcontentloaded", timeout: 60000 });
  } catch (e) {
    // 🔴 导航都超时 = Chrome 状态劣化（reload 循环后页面无法加载，实测踩过）
    //    ⇒ 升级为整机重启浏览器：browser.close + boot()（boot 含金丝雀，完成后 pageReady=true）
    console.log("[dola-signer] goto failed -> full browser relaunch:", e.message);
    try { await browser.close(); } catch {}
    await boot();
    return;
  }
  // 🔴 金丝雀等 hook：mssdk 初始化要数分钟，等到真出 a_bogus 才算 ready
  const deadline = Date.now() + 8 * 60 * 1000;
  let ready = false;
  while (Date.now() < deadline) {
    await new Promise((r) => setTimeout(r, 15000));
    try {
      const u = await mintOnce("https://www.dola.com/chat/completion?aid=495671&canary=1", "POST", "{}");
      ready = !!u;
      break;
    } catch { /* 还没就绪，继续等 */ }
  }
  pageReady = true;
  console.log(`[dola-signer] page reloaded, canary ${ready ? "ok" : "TIMEOUT (8min)"}`);
}

/** 页面内发起 fetch 触发 SDK 签名；等拦截器抓到签名 URL。
 *  超时 ⇒ 刷新页面自愈后重试一次（页面久驻后 SDK 会哑，实弹踩过）。 */
async function mintSignedUrl(url, method, body) {
  if (!pageReady) throw new Error("signer page not ready");
  try {
    return await mintOnce(url, method, body);
  } catch (e) {
    await reloadPage();
    const signed = await mintOnce(url, method, body);
    if (!signed) throw new Error("mint failed after page reload");
    return signed;
  }
}

const pendingMints = [];
let UA_USED = "";

function readBody(req) {
  return new Promise((resolve, reject) => {
    let data = "";
    req.on("data", (c) => (data += c));
    req.on("end", () => resolve(data));
    req.on("error", reject);
  });
}

// ===== 🔴 签名池（预取）：a_bogus 只绑 URL 不绑 body（2026-10-12 实测）=====
// 服务侧 /chat/completion 的 URL 恒定（common_query 固定）⇒ 预铸签名可复用任意 body。
// 池既是零延迟预取，也是 hook 保活（每 20s 真实铸签一次）。
const POOL_URL = process.env.POOL_URL || "";
const POOL_SIZE = parseInt(process.env.POOL_SIZE || "12", 10);
const POOL_TTL_MS = 4 * 60 * 1000;   // a_bogus TTL ≥5min，留 1min 安全边际
const sigPool = [];                   // [{url, at}] 按时间升序

async function poolFiller() {
  if (!POOL_URL || !pageReady) return;
  const now = Date.now();
  while (sigPool.length && now - sigPool[0].at > POOL_TTL_MS) sigPool.shift();
  if (sigPool.length >= POOL_SIZE) return;
  if (pendingMints.some((p) => !p.done)) return; // 真实铸签优先
  try {
    const signed = await mintOnce(POOL_URL, "POST", "{}");
    sigPool.push({ url: signed, at: Date.now() });
    poolFailStreak = 0;
  } catch (e) {
    poolFailStreak += 1;
    if (poolFailStreak >= 3) {  // 会话死了：连续 3 次（~1min）触发自愈 reload
      console.log("[dola-signer] pool fill fail x3 -> reload:", e.message);
      poolFailStreak = 0;
      try { await reloadPage(); } catch (e2) { console.log("[dola-signer] reload err:", e2.message); }
    }
  }
}
let poolFailStreak = 0;
setInterval(() => { poolFiller().catch(() => {}); }, 20 * 1000).unref();

// 🔴 周期金丝雀保活：mssdk 会话 ~30 分钟过期，每 10 分钟验一次；
//    失败先 60s 后重试一次（瞬时抖动不 reload），连续两次失败才 reload
//    （频繁 reload 反而触发上游会话清除，实测踩过）
const KEEPALIVE_MS = 10 * 60 * 1000;
let keepaliveFails = 0;
let keepaliveTimer = setInterval(async () => {
  if (!pageReady) return;
  if (pendingMints.some((p) => !p.done)) return; // 🔴 有真实铸签在途，避免同 prefix 交叉匹配
  try {
    await mintOnce("https://www.dola.com/chat/completion?aid=495671&keepalive=1", "POST", "{}");
    keepaliveFails = 0;
  } catch (e) {
    keepaliveFails += 1;
    console.log(`[dola-signer] keepalive fail #${keepaliveFails}:`, e.message);
    if (keepaliveFails < 2) return; // 第一次失败：等下轮（10min 后）再判，不急着 reload
    try { await reloadPage(); keepaliveFails = 0; }
    catch (e2) { console.log("[dola-signer] reload failed:", e2.message); }
  }
}, KEEPALIVE_MS);
keepaliveTimer.unref();

const server = http.createServer(async (req, res) => {
  try {
    if (req.method === "GET" && req.url === "/healthz") {
      res.writeHead(200, { "content-type": "application/json" });
      res.end(JSON.stringify({ ok: !!browser, page_ready: pageReady }));
      return;
    }
    if (req.method === "GET" && req.url === "/pageinfo") {
    page.cookies("https://www.dola.com").then((cookies) => {
      const ms = (cookies.find((c) => c.name === "msToken") || {}).value || "";
      res.writeHead(200, { "content-type": "application/json" });
      res.end(JSON.stringify({ msToken: ms, ua: UA_USED || "", cookie_names: cookies.map((c) => c.name) }));
    }).catch((e) => {
      res.writeHead(500, { "content-type": "application/json" });
      res.end(JSON.stringify({ error: e.message }));
    });
    return;
  }

  // 🔴 页面真发：真 Chrome TLS + 真指纹 + 页面 cookie 原生请求（绕 JA3/TLS 检测）
  //    {cookie, url(已带 a_bogus), body} → 注入 cookie → 页面 fetch 读 SSE 头部 → 返回文本
  if (req.method === "POST" && req.url === "/send") {
    const raw = await readBody(req);
    const { cookie, url: sendUrl, body: sendBody } = JSON.parse(raw || "{}");
    if (!sendUrl || !sendBody) {
      res.writeHead(400, { "content-type": "application/json" });
      res.end(JSON.stringify({ error: "url/body required" }));
      return;
    }
    // 注入 cookie（解析 kv 对，仅覆盖发送所需会话）
    if (cookie) {
      const pairs = cookie.split(";").map((p) => p.trim()).filter(Boolean)
        .map((p) => {
          const i = p.indexOf("=");
          return { name: p.slice(0, i), value: p.slice(i + 1) };
        })
        .map((c) => ({ ...c, domain: ".dola.com", path: "/" }));
      await page.setCookie(...pairs).catch(() => {});
    }
    const text = await page.evaluate(async (u, b) => {
      try {
        const r = await fetch(u, {
          method: "POST", body: b, credentials: "include",
          headers: { "content-type": "application/json; encoding=utf-8" },
        });
        const ct = r.headers.get("content-type") || "";
        if (!ct.includes("event-stream")) {
          return "HTTP " + r.status + " " + (await r.text()).slice(0, 200);
        }
        const reader = r.body.getReader();
        const dec = new TextDecoder();
        let out = "";
        const deadline = Date.now() + 20000;   // 读 SSE 头部（ACK 或错误码足够）
        while (Date.now() < deadline && out.length < 4096) {
          const { done, value } = await reader.read();
          if (done) break;
          out += dec.decode(value, { stream: true });
          if (out.includes("STREAM_ERROR") || out.includes("SSE_ACK")) break;
        }
        try { reader.cancel(); } catch {}
        return out.slice(0, 4096);
      } catch (e) {
        return "FETCH_ERR " + e.message;
      }
    }, sendUrl, sendBody);
    res.writeHead(200, { "content-type": "application/json" });
    res.end(JSON.stringify({ sse_head: text }));
    return;
  }

  if (req.method === "POST" && req.url === "/sign") {
      const raw = await readBody(req);
      const { url, method = "POST", body = "" } = JSON.parse(raw || "{}");
      if (!url || !url.startsWith("https://www.dola.com/")) {
        res.writeHead(400, { "content-type": "application/json" });
        res.end(JSON.stringify({ error: "url 必须是 dola.com 绝对地址" }));
        return;
      }
      // 🔴 签名池命中（URL 严格相等）：零延迟返回预铸签名
      if (POOL_URL && url === POOL_URL) {
        const now2 = Date.now();
        while (sigPool.length && now2 - sigPool[0].at > POOL_TTL_MS) sigPool.shift();
        if (sigPool.length) {
          const entry = sigPool.shift();
          res.writeHead(200, { "content-type": "application/json" });
          res.end(JSON.stringify({ url: entry.url, pooled: true }));
          return;
        }
      }
      const signed = await mintSignedUrl(url, method, body);
      res.writeHead(200, { "content-type": "application/json" });
      res.end(JSON.stringify({ url: signed }));
      return;
    }
    res.writeHead(404).end();
  } catch (e) {
    res.writeHead(502, { "content-type": "application/json" });
    res.end(JSON.stringify({ error: String((e && e.message) || e) }));
  }
});

if (require.main === module) {
  // 🔴 先 listen 再 boot：HTTP 启动即达（page_ready=false 期间 /sign 快速失败），
  //    否则 boot 的金丝雀等待期（可达数分钟）连接被拒
  server.listen(PORT, "0.0.0.0", () =>
    console.log(`[dola-signer] listening on ${PORT} (page booting...)`)
  );
  boot().catch((e) => {
    bootError = e;
    console.error("[dola-signer] boot failed:", e);
    process.exit(1);
  });
}

module.exports = { boot, mintSignedUrl, _server: server };
