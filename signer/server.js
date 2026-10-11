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
const puppeteer = require("puppeteer-core");

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
  const args = ["--no-sandbox", "--disable-blink-features=AutomationControlled"];
  if (PROXY) args.push(`--proxy-server=${PROXY}`);
  browser = await puppeteer.launch({
    executablePath: CHROME_PATH,
    headless: "new",
    args,
  });
  page = await browser.newPage();
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
  await page.goto(PAGE_URL, { waitUntil: "networkidle2", timeout: 45000 });
  pageReady = true;
}

/** 单次铸签尝试。 */
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
  return pending.signedUrl;
}

/** 页面老化自愈：SDK 长时间不开口 ⇒ 刷新页面重新加载 mssdk。 */
async function reloadPage() {
  console.log("[dola-signer] page stale -> reloading");
  pageReady = false;
  await page.goto(PAGE_URL, { waitUntil: "networkidle2", timeout: 45000 });
  pageReady = true;
  console.log("[dola-signer] page reloaded");
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
  boot()
    .then(() => {
      server.listen(PORT, "0.0.0.0", () =>
        console.log(`[dola-signer] ready on 127.0.0.1:${PORT}`)
      );
    })
    .catch((e) => {
      bootError = e;
      console.error("[dola-signer] boot failed:", e);
      process.exit(1);
    });
}

module.exports = { boot, mintSignedUrl, _server: server };
