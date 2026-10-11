#!/usr/bin/env node
/** Debug: 抓 SDK 发出的所有 HTTP 请求 */
const vm = require("vm");
const fs = require("fs");
const path = require("path");
const https = require("https");
const http = require("http");
const { URL: NodeURL } = require("url");

const SDK = path.join(__dirname, "webmssdk.js");
const UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36";

function realFetch(url, opts = {}) {
  return new Promise((resolve, reject) => {
    const u = new NodeURL(url);
    const mod = u.protocol === "https:" ? https : http;
    const reqOpts = {
      hostname: u.hostname, port: u.port || (u.protocol === "https:" ? 443 : 80),
      path: u.pathname + u.search, method: opts.method || "GET",
      headers: { "User-Agent": UA, "Origin": "https://www.dola.com", "Referer": "https://www.dola.com/", ...(opts.headers || {}) },
    };
    const req = mod.request(reqOpts, (res) => {
      let data = "";
      res.on("data", (c) => (data += c));
      res.on("end", () => resolve({ ok: res.statusCode < 400, status: res.statusCode, url, headers: {}, text: () => Promise.resolve(data), json: () => Promise.resolve(JSON.parse(data || "{}")) }));
    });
    req.on("error", (e) => { console.log(`[NET-ERR] ${url}: ${e.message}`); reject(e); });
    if (opts.body) req.write(opts.body);
    req.end();
  });
}

const noop = () => {};
const canvasCtx = { fillText:noop, measureText:()=>({width:100}), getImageData:()=>({data:new Uint8Array(4)}), createLinearGradient:()=>({addColorStop:noop}), arc:noop, fillRect:noop, beginPath:noop, stroke:noop, fill:noop, save:noop, restore:noop, fillStyle:"", font:"", globalAlpha:1 };
const canvas = { width:300, height:150, style:{}, getContext:()=>canvasCtx, toDataURL:()=>"data:image/png;base64,iVBORw0KGgo=", addEventListener:noop };

// 🔴 带日志的 fetch
function loggingFetch(url, opts = {}) {
  console.log(`[FETCH] ${opts.method || "GET"} ${String(url).substring(0, 120)}`);
  if (opts.body) console.log(`[FETCH-BODY] ${String(opts.body).substring(0, 200)}`);
  const urlStr = String(url);
  if (urlStr.includes("dola.com")) {
    console.log(`[INTERCEPT] dola request → capturing URL`);
    if (globalThis.__on_dola_request) globalThis.__on_dola_request(urlStr);
    return Promise.resolve({ url: urlStr, ok: true, status: 200, headers: {}, text: () => Promise.resolve(""), json: () => Promise.resolve({}) });
  }
  return realFetch(urlStr, opts).then(r => {
    console.log(`[FETCH-RES] ${r.status} ${urlStr.substring(0, 80)}`);
    return r;
  });
}

const ctx = vm.createContext({
  document: { cookie:"", title:"Dola", referrer:"", URL:"https://www.dola.com/", documentURI:"https://www.dola.com/", domain:"www.dola.com", host:"www.dola.com", hostname:"www.dola.com", origin:"https://www.dola.com", protocol:"https:", characterSet:"UTF-8", readyState:"complete", visibilityState:"visible", hidden:false, createElement:(t)=>t==="canvas"?{...canvas}:{style:{},appendChild:noop,setAttribute:noop,addEventListener:noop}, createElementNS:(_,t)=>({...canvas}), getElementById:()=>null, querySelector:()=>null, querySelectorAll:()=>[], getElementsByTagName:()=>[], addEventListener:noop, body:{appendChild:noop,style:{}}, head:{appendChild:noop} },
  navigator: { userAgent:UA, appCodeName:"Mozilla", appName:"Netscape", appVersion:UA.replace("Mozilla/",""), platform:"MacIntel", product:"Gecko", vendor:"Google Inc.", language:"zh-CN", languages:["zh-CN","zh","en"], onLine:true, cookieEnabled:true, maxTouchPoints:0, hardwareConcurrency:8, deviceMemory:8, webdriver:false, plugins:{length:0,item:()=>null}, mimeTypes:{length:0}, connection:{effectiveType:"4g"}, javaEnabled:()=>false, sendBeacon:()=>true },
  location: { href:"https://www.dola.com/", hostname:"www.dola.com", host:"www.dola.com", pathname:"/", search:"", hash:"", protocol:"https:", origin:"https://www.dola.com", port:"" },
  screen: { width:1536, height:864, availWidth:1536, availHeight:864, colorDepth:24, pixelDepth:24 },
  history: { length:1, pushState:noop, replaceState:noop },
  innerWidth:1536, innerHeight:742, outerWidth:1536, outerHeight:864, devicePixelRatio:2,
  setTimeout, setInterval, clearTimeout, clearInterval,
  console: { log:(...a)=>console.log("[SDK]",...a), warn:(...a)=>console.log("[SDK-W]",...a), error:(...a)=>console.log("[SDK-E]",...a) },
  JSON, Math, Date, Array, Object, String, Number, Boolean, RegExp, Error, TypeError, Function, Symbol, Map, Set, WeakMap, WeakSet, Promise, Proxy, Reflect,
  Uint8Array, Uint16Array, Uint32Array, Int8Array, Int16Array, Int32Array, Float32Array, Float64Array, ArrayBuffer, DataView, TextEncoder, TextDecoder,
  parseInt, parseFloat, isNaN, isFinite, encodeURIComponent, decodeURIComponent, encodeURI, decodeURI,
  btoa: (s) => Buffer.from(s,"binary").toString("base64"), atob: (s) => Buffer.from(s,"base64").toString("binary"),
  performance, crypto: require("crypto").webcrypto,
  localStorage: {getItem:()=>null,setItem:noop,removeItem:noop},
  sessionStorage: {getItem:()=>null,setItem:noop,removeItem:noop},
  getComputedStyle: () => ({getPropertyValue:()=>""}),
  matchMedia: () => ({matches:false,addListener:noop}),
  addEventListener: noop, removeEventListener: noop, dispatchEvent:()=>true,
  requestAnimationFrame: (fn)=>setTimeout(fn,16),
  Blob, URL: NodeURL, URLSearchParams, alert: noop, confirm: ()=>true,
  fetch: loggingFetch,
  XMLHttpRequest: class {
    open(m,u) { this._url = u; this._m = m; this._h = {}; console.log(`[XHR] ${m} ${String(u).substring(0, 120)}`); }
    setRequestHeader(k,v) { this._h[k] = v; }
    send(body) {
      if (body) console.log(`[XHR-BODY] ${String(body).substring(0, 200)}`);
      const self = this;
      loggingFetch(self._url, { method: self._m, headers: self._h, body }).then(async r => {
        self.status = r.status; self.responseText = await r.text(); self.readyState = 4;
        const text = self.responseText;
        if (text) console.log(`[XHR-RES] ${self.status} ${text.substring(0, 200)}`);
        if (self.onload) self.onload(); if (self.onreadystatechange) self.onreadystatechange();
      }).catch(e => { console.log(`[XHR-ERR] ${e.message}`); self.readyState = 4; if (self.onerror) self.onerror(); });
    }
    abort(){} getAllResponseHeaders(){return ""} getResponseHeader(){return null}
    addEventListener(ev,fn) { if(ev==="load") this.onload=fn; if(ev==="error") this.onerror=fn; if(ev==="readystatechange") this.onreadystatechange=fn; }
  },
});
ctx.window = ctx; ctx.self = ctx; ctx.top = ctx; ctx.parent = ctx; ctx.globalThis = ctx;

// 加载 SDK
console.log("=== loading SDK ===");
vm.runInContext(fs.readFileSync(SDK, "utf-8"), ctx, { timeout: 15000 });
console.log("=== SDK loaded ===");

// init
setTimeout(() => {
  console.log("=== calling init ===");
  try {
    vm.runInContext(`window.byted_acrawler.init({ "aid": 495671 })`, ctx, { timeout: 10000 });
    console.log("init done");
  } catch(e) { console.log("init error:", e.message); }

  // 等 init 完成，然后触发 fetch
  setTimeout(() => {
    console.log("=== triggering fetch ===");
    globalThis.__on_dola_request = (url) => {
      const i = url.indexOf("a_bogus=");
      if (i > -1) {
        console.log(`\n🎉 CAPTURED a_bogus: ${url.substring(i + 8)}`);
      } else {
        console.log(`\n❌ no a_bogus in: ${url.substring(0, 120)}`);
      }
      process.exit(0);
    };
    vm.runInContext(`window.fetch("https://www.dola.com/chat/completion?aid=495671&device_platform=web", {method:"POST", body:"{}"})`, ctx, { timeout: 15000 });
    setTimeout(() => { console.log("timeout waiting for dola request"); process.exit(1); }, 15000);
  }, 5000);
}, 2000);
