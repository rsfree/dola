#!/usr/bin/env node
/** 通过 byted_acrawler 全局对象直接调用 SDK 签名函数 */
const vm = require("vm");
const fs = require("fs");
const path = require("path");

const SDK = path.join(__dirname, "webmssdk.js");
const UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36";

const noop = () => {};
const canvasCtx = {
  fillText: noop, measureText: () => ({width:100}),
  getImageData: () => ({data:new Uint8Array(4)}),
  createLinearGradient: () => ({addColorStop:noop}),
  arc: noop, fillRect: noop, beginPath: noop, closePath: noop, stroke: noop, fill: noop,
  save: noop, restore: noop, translate: noop,
  fillStyle: "", font: "", globalAlpha: 1,
};
const canvas = {
  width: 300, height: 150, style: {},
  getContext: () => canvasCtx,
  toDataURL: () => "data:image/png;base64,iVBORw0KGgo=",
  addEventListener: noop,
};
const gl = {
  getExtension: (n) => n==="WEBGL_debug_renderer_info" ? {UNMASKED_VENDOR_WEBGL:0x9245,UNMASKED_RENDERER_WEBGL:0x9246} : null,
  getParameter: (p) => p===0x9245 ? "Apple" : p===0x9246 ? "Apple M2" : "",
  createBuffer: ()=>({}), bindBuffer: noop, bufferData: noop,
  createProgram: ()=>({}), createShader: ()=>({}),
  shaderSource: noop, compileShader: noop, attachShader: noop, linkProgram: noop, useProgram: noop,
  getShaderParameter: ()=>true, getProgramParameter: ()=>true,
  canvas,
};

const ctx = vm.createContext({
  document: {
    cookie: "", title: "Dola", referrer: "",
    URL: "https://www.dola.com/", documentURI: "https://www.dola.com/",
    domain: "www.dola.com", host: "www.dola.com", hostname: "www.dola.com",
    origin: "https://www.dola.com", protocol: "https:",
    characterSet: "UTF-8", readyState: "complete", visibilityState: "visible", hidden: false,
    createElement: (tag) => tag === "canvas" ? {...canvas} : { style:{}, appendChild:noop, setAttribute:noop, addEventListener:noop },
    createElementNS: (_, tag) => ({...canvas}),
    getElementById: () => null, querySelector: () => null, querySelectorAll: () => [],
    getElementsByTagName: () => [], addEventListener: noop,
    body: { appendChild: noop, style: {} }, head: { appendChild: noop },
  },
  navigator: {
    userAgent: UA, appCodeName: "Mozilla", appName: "Netscape",
    appVersion: UA.replace("Mozilla/",""), platform: "MacIntel", product: "Gecko",
    vendor: "Google Inc.", language: "zh-CN", languages: ["zh-CN","zh","en"],
    onLine: true, cookieEnabled: true, maxTouchPoints: 0,
    hardwareConcurrency: 8, deviceMemory: 8, webdriver: false,
    plugins: {length:0, item:()=>null}, mimeTypes: {length:0},
    connection: {effectiveType:"4g", rtt:50, downlink:10},
    javaEnabled: () => false, sendBeacon: () => true,
  },
  location: {
    href: "https://www.dola.com/", hostname: "www.dola.com", host: "www.dola.com",
    pathname: "/", search: "", hash: "", protocol: "https:", origin: "https://www.dola.com", port: "",
  },
  screen: { width:1536, height:864, availWidth:1536, availHeight:864, colorDepth:24, pixelDepth:24 },
  history: { length: 1, pushState: noop, replaceState: noop },
  innerWidth: 1536, innerHeight: 742, outerWidth: 1536, outerHeight: 864,
  devicePixelRatio: 2, screenX: 0, screenY: 0,
  setTimeout, setInterval, clearTimeout, clearInterval,
  console: { log: noop, warn: noop, error: noop, info: noop, debug: noop },
  JSON, Math, Date, Array, Object, String, Number, Boolean, RegExp, Error, TypeError,
  Function, Symbol, Map, Set, WeakMap, WeakSet, Promise, Proxy, Reflect,
  Uint8Array, Uint16Array, Uint32Array, Int8Array, Int16Array, Int32Array,
  Float32Array, Float64Array, ArrayBuffer, DataView, TextEncoder, TextDecoder,
  parseInt, parseFloat, isNaN, isFinite,
  encodeURIComponent, decodeURIComponent, encodeURI, decodeURI,
  btoa: (s) => Buffer.from(s, "binary").toString("base64"),
  atob: (s) => Buffer.from(s, "base64").toString("binary"),
  performance,
  fetch: function(url, opts) { return Promise.resolve({url:String(url), ok:true, status:200}); },
  XMLHttpRequest: class { open(){} send(){} setRequestHeader(){} addEventListener(){} },
  crypto: require("crypto").webcrypto,
  localStorage: {getItem:()=>null,setItem:noop,removeItem:noop},
  sessionStorage: {getItem:()=>null,setItem:noop,removeItem:noop},
  getComputedStyle: () => ({getPropertyValue:()=>""}),
  matchMedia: () => ({matches:false,addListener:noop}),
  addEventListener: noop, removeEventListener: noop, dispatchEvent: () => true,
  requestAnimationFrame: (fn) => setTimeout(fn, 16),
  Blob, URL, URLSearchParams,
  alert: noop, confirm: () => true,
});
ctx.window = ctx; ctx.self = ctx; ctx.top = ctx; ctx.parent = ctx; ctx.globalThis = ctx;

console.log("loading SDK...");
const src = fs.readFileSync(SDK, "utf-8");
vm.runInContext(src, ctx, { filename: "webmssdk.js", timeout: 15000 });
console.log("SDK loaded");

setTimeout(() => {
  // 检查可用的签名全局变量
  for (const key of ["byted_acrawler", "bytedSDK", "TCSign", "_bytedAcrawler", "acs", "byted_acrawler_sign"]) {
    try {
      const t = vm.runInContext(`typeof ${key}`, ctx);
      if (t !== "undefined") {
        const val = vm.runInContext(`${key}`, ctx);
        const keys = vm.runInContext(`Object.keys(${key} || {})`, ctx);
        console.log(`✅ ${key}: ${t}, keys: ${JSON.stringify(keys)}`);
      }
    } catch(e) { /* ignore */ }
  }

  // 尝试 byted_acrawler.frontierSign（标准 ByteDance 签名接口）
  try {
    const result = vm.runInContext(`
      (function() {
        if (window.byted_acrawler && window.byted_acrawler.frontierSign) {
          return window.byted_acrawler.frontierSign(${JSON.stringify("https://www.dola.com/chat/completion?aid=495671&device_platform=web")});
        }
        if (window.byted_acrawler && window.byted_acrawler.sign) {
          return window.byted_acrawler.sign(${JSON.stringify("https://www.dola.com/chat/completion?aid=495671&device_platform=web")});
        }
        return "no sign function found";
      })()
    `, ctx, { timeout: 5000 });
    console.log("sign result:", JSON.stringify(result).substring(0, 200));
  } catch(e) {
    console.log("sign error:", e.message.slice(0, 200));
  }
}, 5000);
