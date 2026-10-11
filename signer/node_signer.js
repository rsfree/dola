/**
 * webmssdk Node.js Runner — 无浏览器依赖的 a_bogus 铸签服务
 *
 * 原理：加载 webmssdk.js（ByteDance 签名 SDK），mock 浏览器环境，
 *       直接调用 SDK 的 fetch hook 生成 a_bogus，无需 Chromium。
 *
 * 端点：POST /sign { url, method, body } → { url: signed_url }
 */
const http = require("http");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const PORT = parseInt(process.env.PORT || "8491", 10);
const SDK_PATH = path.join(__dirname, "webmssdk.js");
const DOLA_COOKIE = process.env.DOLA_COOKIE || "";
const PAGE_URL = "https://www.dola.com/chat/create-image";

// ---- 浏览器环境 mock ----

function createBrowserEnv(userAgent) {
  const listeners = {};
  const noop = () => {};

  // canvas mock
  const canvasCtx = {
    fillText: noop, strokeText: noop, measureText: () => ({ width: 100 }),
    getImageData: () => ({ data: new Uint8Array(4) }),
    putImageData: noop, drawImage: noop,
    createLinearGradient: () => ({ addColorStop: noop }),
    createRadialGradient: () => ({ addColorStop: noop }),
    createPattern: () => ({}),
    arc: noop, fillRect: noop, strokeRect: noop, clearRect: noop,
    beginPath: noop, closePath: noop, moveTo: noop, lineTo: noop,
    stroke: noop, fill: noop, save: noop, restore: noop,
    translate: noop, rotate: noop, scale: noop,
    fillStyle: "", strokeStyle: "", font: "", globalAlpha: 1,
    globalCompositeOperation: "source-over", textAlign: "start",
    textBaseline: "alphabetic", lineWidth: 1,
  };
  const canvas = {
    width: 300, height: 150, style: {},
    getContext: () => canvasCtx,
    toDataURL: () => "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
    addEventListener: noop,
  };

  // webgl mock
  const gl = {
    getExtension: (name) => {
      if (name === "WEBGL_debug_renderer_info")
        return { UNMASKED_VENDOR_WEBGL: 0x9245, UNMASKED_RENDERER_WEBGL: 0x9246 };
      return null;
    },
    getParameter: (param) => {
      if (param === 0x9245) return "Google Inc. (Apple)";
      if (param === 0x9246) return "ANGLE Metal Renderer: Apple M2";
      return "";
    },
    createBuffer: () => ({}), bindBuffer: noop, bufferData: noop,
    createProgram: () => ({}), createShader: () => ({}),
    shaderSource: noop, compileShader: noop, attachShader: noop,
    linkProgram: noop, useProgram: noop,
    getShaderParameter: () => true, getProgramParameter: () => true,
    getAttribLocation: () => 0, getUniformLocation: () => ({}),
    enableVertexAttribArray: noop, vertexAttribPointer: noop,
    uniform1f: noop, uniform2f: noop, uniform4fv: noop,
    drawArrays: noop, viewport: noop,
    canvas, drawingBufferWidth: 300, drawingBufferHeight: 150,
  };

  const document = {
    cookie: DOLA_COOKIE,
    title: "Dola",
    referrer: "",
    URL: PAGE_URL, documentURI: PAGE_URL, baseURI: PAGE_URL,
    domain: "www.dola.com", host: "www.dola.com", hostname: "www.dola.com",
    origin: "https://www.dola.com", protocol: "https:",
    characterSet: "UTF-8", charset: "UTF-8", contentType: "text/html",
    readyState: "complete", visibilityState: "visible", hidden: false,
    createElement: (tag) => {
      if (tag === "canvas") return { ...canvas };
      return {
        style: {}, appendChild: noop, setAttribute: noop,
        getAttribute: () => null, innerHTML: "", textContent: "",
        addEventListener: noop, removeEventListener: noop,
      };
    },
    createElementNS: (ns, tag) => document.createElement(tag),
    getElementById: () => null,
    querySelector: () => null,
    querySelectorAll: () => [],
    getElementsByTagName: () => [],
    addEventListener: noop, removeEventListener: noop,
    createEvent: () => ({ initEvent: noop }),
    body: { appendChild: noop, style: {} },
    head: { appendChild: noop },
    documentElement: { style: {} },
    scripts: [], forms: [], images: [], links: [],
    hasFocus: () => true,
    createTextNode: () => ({}),
    attachEvent: undefined,
  };

  const navigator = {
    userAgent,
    appCodeName: "Mozilla",
    appName: "Netscape",
    appVersion: userAgent.replace("Mozilla/", ""),
    platform: "MacIntel",
    product: "Gecko",
    productSub: "20030107",
    vendor: "Google Inc.",
    vendorSub: "",
    language: "zh-CN",
    languages: ["zh-CN", "zh", "en"],
    onLine: true,
    cookieEnabled: true,
    doNotTrack: null,
    maxTouchPoints: 0,
    hardwareConcurrency: 8,
    deviceMemory: 8,
    connection: { effectiveType: "4g", rtt: 50, downlink: 10, saveData: false },
    plugins: { length: 0, item: () => null, namedItem: () => null, refresh: noop },
    mimeTypes: { length: 0 },
    webdriver: false,
    pdfViewerEnabled: true,
    getBattery: () => Promise.resolve({ charging: true, level: 1 }),
    getGamepads: () => [],
    javaEnabled: () => false,
    sendBeacon: () => true,
    vibrate: () => true,
  };

  const location = {
    href: PAGE_URL, hostname: "www.dola.com", host: "www.dola.com",
    pathname: "/chat/create-image", search: "", hash: "",
    protocol: "https:", origin: "https://www.dola.com", port: "",
    assign: noop, replace: noop, reload: noop,
  };

  const screen = {
    width: 1536, height: 864, availWidth: 1536, availHeight: 864,
    colorDepth: 24, pixelDepth: 24, availLeft: 0, availTop: 0,
    orientation: { type: "landscape-primary", angle: 0 },
  };

  const history = { length: 1, back: noop, forward: noop, go: noop, pushState: noop, replaceState: noop };

  const window = {
    // 核心对象
    document, navigator, location, screen, history,
    // 全局函数
    setTimeout, setInterval, clearTimeout, clearInterval,
    parseInt, parseFloat, isNaN, isFinite,
    encodeURIComponent, decodeURIComponent, encodeURI, decodeURI,
    JSON, Math, Date, Array, Object, String, Number, Boolean, RegExp,
    Error, TypeError, RangeError, SyntaxError, Function, Symbol,
    Map, Set, WeakMap, WeakSet, Promise, Proxy, Reflect,
    Uint8Array, Uint16Array, Uint32Array, Int8Array, Int16Array, Int32Array,
    Float32Array, Float64Array, ArrayBuffer, DataView, TextEncoder, TextDecoder,
    Blob, URL, URLSearchParams, FormData, Headers, Request, Response,
    // 浏览器特有
    innerWidth: 1536, innerHeight: 742,
    outerWidth: 1536, outerHeight: 864,
    screenX: 0, screenY: 0, pageXOffset: 0, pageYOffset: 0,
    scrollX: 0, scrollY: 0, devicePixelRatio: 2,
    addEventListener: (type, fn) => { (listeners[type] = listeners[type] || []).push(fn); },
    removeEventListener: noop,
    dispatchEvent: () => true,
    requestAnimationFrame: (fn) => setTimeout(fn, 16),
    cancelAnimationFrame: clearTimeout,
    getComputedStyle: () => ({ getPropertyValue: () => "" }),
    matchMedia: () => ({ matches: false, addListener: noop, removeListener: noop }),
    btoa: (s) => Buffer.from(s, "binary").toString("base64"),
    atob: (s) => Buffer.from(s, "base64").toString("binary"),
    fetch: (url, opts) => {
      // 🔴 真实 fetch（Node 18+ 内置），SDK 用它与 mssdk.bytedance.com 通信拿密钥
      return globalThis.fetch(url, opts);
    },
    XMLHttpRequest: class XMLHttpRequestPolyfill {
      constructor() { this.readyState = 0; this.status = 0; this.responseText = ""; this.response = ""; this.statusText = ""; this.responseURL = ""; }
      open(method, url, async) { this._method = method; this._url = url; this._headers = {}; this.readyState = 1; }
      setRequestHeader(k, v) { this._headers[k] = v; }
      send(body) {
        const self = this;
        const fetchOpts = { method: self._method, headers: self._headers };
        if (body) fetchOpts.body = body;
        globalThis.fetch(self._url, fetchOpts).then(async r => {
          self.status = r.status;
          self.statusText = r.statusText;
          self.responseURL = r.url;
          self.responseText = await r.text();
          self.response = self.responseText;
          self.readyState = 4;
          if (self.onreadystatechange) self.onreadystatechange();
          if (self.onload) self.onload();
        }).catch(e => {
          self.status = 0; self.readyState = 4;
          if (self.onerror) self.onerror(e);
          if (self.onreadystatechange) self.onreadystatechange();
        });
      }
      abort() {}
      getAllResponseHeaders() { return ""; }
      getResponseHeader() { return null; }
      addEventListener(ev, fn) { if (ev === "load") this.onload = fn; if (ev === "error") this.onerror = fn; }
      removeEventListener() {}
    },
    crypto: require("crypto").webcrypto,
    performance,
    localStorage: { getItem: () => null, setItem: noop, removeItem: noop, clear: noop, length: 0 },
    sessionStorage: { getItem: () => null, setItem: noop, removeItem: noop, clear: noop, length: 0 },
    indexedDB: { open: () => ({}) },
    Notification: { permission: "default", requestPermission: () => Promise.resolve("default") },
    alert: noop, confirm: () => true, prompt: () => null,
    open: noop, close: noop, focus: noop, blur: noop,
    print: noop, stop: noop, scroll: noop, scrollTo: noop, scrollBy: noop,
    // 自身引用
    self: null, top: null, parent: null, frames: null, globalThis: null,
  };
  window.self = window; window.top = window; window.parent = window;
  window.frames = window; window.globalThis = window; window.window = window;

  return { window, document, navigator, location, screen, listeners };
}

// ---- 加载 SDK ----

let sdkContext = null;

function initSDK(userAgent) {
  const source = fs.readFileSync(SDK_PATH, "utf-8");
  const env = createBrowserEnv(userAgent);
  const context = vm.createContext(env.window);
  vm.runInContext(source, context, { filename: "webmssdk.js", timeout: 10000 });
  sdkContext = context;
  return context;
}

// ---- HTTP 服务 ----

const server = http.createServer((req, res) => {
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Content-Type", "application/json");

  if (req.method === "GET" && req.url === "/healthz") {
    res.writeHead(200);
    res.end(JSON.stringify({ ok: true, mode: "node-sdk", sdk_loaded: !!sdkContext }));
    return;
  }

  if (req.method === "POST" && req.url === "/sign") {
    let body = "";
    req.on("data", (c) => (body += c));
    req.on("end", () => {
      try {
        const { url, method, body: reqBody, ua } = JSON.parse(body);
        const userAgent = ua || "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36";

        if (!sdkContext) initSDK(userAgent);

        // 在 SDK 上下文中执行 fetch（SDK 会 hook 并加 a_bogus）
        // 由于 SDK hook 了 window.fetch，我们通过 VM 调用它
        const script = new vm.Script(`
          (function() {
            return new Promise((resolve, reject) => {
              const timeout = setTimeout(() => reject(new Error("mint timeout")), ${process.env.MINT_TIMEOUT_MS || 20000});
              window.fetch(${JSON.stringify(url)}, {
                method: ${JSON.stringify(method || "POST")},
                body: ${JSON.stringify(reqBody || null)},
                headers: { "content-type": "application/json; encoding=utf-8" },
              }).then(r => {
                clearTimeout(timeout);
                resolve(r.url);
              }).catch(e => {
                clearTimeout(timeout);
                reject(e);
              });
            });
          })()
        `);

        const promise = script.runInContext(sdkContext, { timeout: 25000 });
        promise
          .then((signedUrl) => {
            res.writeHead(200);
            res.end(JSON.stringify({ url: signedUrl }));
          })
          .catch((e) => {
            res.writeHead(502);
            res.end(JSON.stringify({ error: { code: "mint_error", message: e.message } }));
          });
      } catch (e) {
        res.writeHead(500);
        res.end(JSON.stringify({ error: { code: "internal", message: e.message } }));
      }
    });
    return;
  }

  res.writeHead(404);
  res.end(JSON.stringify({ error: "not found" }));
});

server.listen(PORT, "0.0.0.0", () => {
  console.log(`[node-signer] listening on :${PORT} (SDK: ${fs.existsSync(SDK_PATH) ? "found" : "MISSING"})`);
  if (fs.existsSync(SDK_PATH)) {
    try {
      initSDK("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36");
      console.log("[node-signer] SDK pre-initialized");
    } catch (e) {
      console.error("[node-signer] SDK init failed:", e.message);
    }
  }
});
