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
    "--window-size=1536,864",
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
  await page.setUserAgent(
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 " +
      "(KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36"
  );
  await page.setViewport({ width: 1440, height: 900 });
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
  await page.goto(PAGE_URL, { waitUntil: "domcontentloaded", timeout: 60000 });
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

function readBody(req) {
  return new Promise((resolve, reject) => {
    let data = "";
    req.on("data", (c) => (data += c));
    req.on("end", () => resolve(data));
    req.on("error", reject);
  });
}

// 🔴 周期金丝雀保活：mssdk 会话 ~30 分钟过期，每 4 分钟验一次，哑了后台自愈
const KEEPALIVE_MS = 4 * 60 * 1000;
let keepaliveTimer = setInterval(async () => {
  if (!pageReady) return;
  if (pendingMints.some((p) => !p.done)) return; // 🔴 有真实铸签在途，避免同 prefix 交叉匹配
  try {
    await mintOnce("https://www.dola.com/chat/completion?aid=495671&keepalive=1", "POST", "{}");
  } catch (e) {
    console.log("[dola-signer] keepalive mint failed -> reloading:", e.message);
    try { await reloadPage(); } catch (e2) { console.log("[dola-signer] reload failed:", e2.message); }
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
    if (req.method === "POST" && req.url === "/sign") {
      const raw = await readBody(req);
      const { url, method = "POST", body = "" } = JSON.parse(raw || "{}");
      if (!url || !url.startsWith("https://www.dola.com/")) {
        res.writeHead(400, { "content-type": "application/json" });
        res.end(JSON.stringify({ error: "url 必须是 dola.com 绝对地址" }));
        return;
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
