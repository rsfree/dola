#!/usr/bin/env node
/** SDK init → fetch hook → 拦截 dola 请求捕获 a_bogus */
const vm = require("vm");
const fs = require("fs");
const path = require("path");
const https = require("https");
const http = require("http");
const { URL: NodeURL } = require("url");

const SDK = path.join(__dirname, "webmssdk.js");
const UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36";

// 真实 fetch（允许通过，SDK 用它与 mssdk 通信）
function realFetch(url, opts = {}) {
  return new Promise((resolve, reject) => {
    const u = new NodeURL(url);
    const mod = u.protocol === "https:" ? https : http;
    const reqOpts = {
      hostname: u.hostname, port: u.port || (u.protocol === "https:" ? 443 : 80),
      path: u.pathname + u.search, method: opts.method || "GET",
      headers: { "User-Agent": UA, ...(opts.headers || {}) },
    };
    const req = mod.request(reqOpts, (res) => {
      let data = "";
      res.on("data", (c) => (data += c));
      res.on("end", () => {
        resolve({
          ok: res.statusCode >= 200 && res.statusCode < 300,
          status: res.statusCode, statusText: res.statusMessage,
          url: url, headers: Object.fromEntries(Object.entries(res.headers)),
          text: () => Promise.resolve(data),
          json: () => Promise.resolve(JSON.parse(data)),
        });
      });
    });
    req.on("error", reject);
    if (opts.body) req.write(opts.body);
    req.end();
  });
}

// 环境
const noop = () => {};
const canvasCtx = { fillText:noop, measureText:()=>({width:100}), getImageData:()=>({data:new Uint8Array(4)}), createLinearGradient:()=>({addColorStop:noop}), arc:noop, fillRect:noop, beginPath:noop, stroke:noop, fill:noop, save:noop, restore:noop, fillStyle:"", font:"", globalAlpha:1 };
const canvas = { width:300, height:150, style:{}, getContext:()=>canvasCtx, toDataURL:()=>"data:image/png;base64,iVBORw0KGgo=", addEventListener:noop };
const gl = { getExtension:(n)=>n==="WEBGL_debug_renderer_info"?{UNMASKED_VENDOR_WEBGL:0x9245,UNMASKED_RENDERER_WEBGL:0x9246}:null, getParameter:(p)=>p===0x9245?"Apple":p===0x9246?"Apple M2":"", createBuffer:()=>({}), bindBuffer:noop, bufferData:noop, createProgram:()=>({}), createShader:()=>({}), shaderSource:noop, compileShader:noop, attachShader:noop, linkProgram:noop, useProgram:noop, getShaderParameter:()=>true, getProgramParameter:()=>true, canvas };

const ctx = vm.createContext({
  document: { cookie:"", title:"Dola", referrer:"", URL:"https://www.dola.com/", documentURI:"https://www.dola.com/", domain:"www.dola.com", host:"www.dola.com", hostname:"www.dola.com", origin:"https://www.dola.com", protocol:"https:", characterSet:"UTF-8", readyState:"complete", visibilityState:"visible", hidden:false, createElement:(t)=>t==="canvas"?{...canvas}:{style:{},appendChild:noop,setAttribute:noop,addEventListener:noop}, createElementNS:(_,t)=>({...canvas}), getElementById:()=>null, querySelector:()=>null, querySelectorAll:()=>[], getElementsByTagName:()=>[], addEventListener:noop, body:{appendChild:noop,style:{}}, head:{appendChild:noop} },
  navigator: { userAgent:UA, appCodeName:"Mozilla", appName:"Netscape", appVersion:UA.replace("Mozilla/",""), platform:"MacIntel", product:"Gecko", vendor:"Google Inc.", language:"zh-CN", languages:["zh-CN","zh","en"], onLine:true, cookieEnabled:true, maxTouchPoints:0, hardwareConcurrency:8, deviceMemory:8, webdriver:false, plugins:{length:0,item:()=>null}, mimeTypes:{length:0}, connection:{effectiveType:"4g"}, javaEnabled:()=>false, sendBeacon:()=>true },
  location: { href:"https://www.dola.com/", hostname:"www.dola.com", host:"www.dola.com", pathname:"/", search:"", hash:"", protocol:"https:", origin:"https://www.dola.com", port:"" },
  screen: { width:1536, height:864, availWidth:1536, availHeight:864, colorDepth:24, pixelDepth:24 },
  history: { length:1, pushState:noop, replaceState:noop },
  innerWidth:1536, innerHeight:742, outerWidth:1536, outerHeight:864, devicePixelRatio:2,
  setTimeout, setInterval, clearTimeout, clearInterval,
  console: { log:(...a)=>console.log("[SDK]",...a), warn:noop, error:(...a)=>console.error("[SDK-ERR]",...a), info:noop },
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
  Blob, URL: NodeURL, URLSearchParams,
  alert: noop, confirm: ()=>true,
  // 🔴 关键：SDK init 时用真 fetch 连 mssdk.bytedance.com；对 dola.com 的请求捕获 URL 不发送
  fetch: function(url, opts) {
    const urlStr = String(url);
    if (urlStr.includes("dola.com") || urlStr.includes("chat/completion")) {
      // 拦截 dola 请求 → 捕获 signed URL
      if (globalThis.__captured_url) {
        const captured = globalThis.__captured_url;
        globalThis.__captured_url = null;
        return Promise.resolve({ url: captured, ok: true, status: 200, headers: {}, text: () => Promise.resolve(""), json: () => Promise.resolve({}) });
      }
    }
    // mssdk.bytedance.com 等非 dola 请求 → 真实发送
    return realFetch(urlStr, opts);
  },
  XMLHttpRequest: class {
    open(m,u) { this._url = u; this._m = m; this._h = {}; }
    setRequestHeader(k,v) { this._h[k] = v; }
    send(body) {
      const self = this;
      if (self._url && self._url.includes("dola.com")) {
        if (globalThis.__captured_url) {
          const captured = globalThis.__captured_url;
          globalThis.__captured_url = null;
          self.status = 200; self.responseText = ""; self.readyState = 4;
          if (self.onload) self.onload();
          if (self.onreadystatechange) self.onreadystatechange();
          return;
        }
      }
      realFetch(self._url, { method: self._m, headers: self._h, body }).then(async r => {
        self.status = r.status; self.responseText = await r.text(); self.readyState = 4;
        if (self.onload) self.onload(); if (self.onreadystatechange) self.onreadystatechange();
      }).catch(() => { self.readyState = 4; if (self.onerror) self.onerror(); });
    }
    abort(){} getAllResponseHeaders(){return ""} getResponseHeader(){return null}
    addEventListener(ev,fn) { if(ev==="load") this.onload=fn; }
  },
});
ctx.window = ctx; ctx.self = ctx; ctx.top = ctx; ctx.parent = ctx; ctx.globalThis = ctx;

// 加载 SDK
console.log("loading webmssdk...");
vm.runInContext(fs.readFileSync(SDK, "utf-8"), ctx, { filename: "webmssdk.js", timeout: 15000 });
console.log("SDK loaded");

// init SDK（连接 mssdk.bytedance.com 拿密钥）
setTimeout(async () => {
  try {
    vm.runInContext(`window.byted_acrawler.init({ "aid": 495671 })`, ctx, { timeout: 10000 });
    console.log("SDK init called");
  } catch(e) { console.log("init result:", e.message); }

  // 等 SDK 初始化完成
  setTimeout(async () => {
    try {
      // 设置要签名的 URL
      const targetUrl = "https://www.dola.com/chat/completion?aid=495671&device_platform=web";
      globalThis.__captured_url = targetUrl;

      // 触发 fetch → SDK hook 应该加 a_bogus → 我们的拦截器捕获
      const promise = vm.runInContext(`
        window.fetch("${targetUrl}", { method: "POST", body: "{}" }).then(r => r.url)
      `, ctx, { timeout: 20000 });

      const signedUrl = await promise;
      const i = signedUrl.indexOf("a_bogus=");
      if (i > -1) {
        const ab = signedUrl.substring(i + 8);
        console.log(`✅ a_bogus (${ab.length} chars): ${decodeURIComponent(ab).substring(0, 80)}`);
      } else {
        console.log("❌ no a_bogus in URL:", signedUrl.substring(0, 120));
      }
    } catch(e) {
      console.log("fetch error:", e.message);
    }
    process.exit(0);
  }, 5000); // 等 5 秒让 SDK init 完成
}, 2000);
