/* 终极商城 —— 页面逻辑：token 管理 + 抢购 + 库存轮询 */
const TOKEN_KEY = "shop_token";
const API = "";   // 同源

function getToken() { return localStorage.getItem(TOKEN_KEY) || ""; }
function setToken(t) { localStorage.setItem(TOKEN_KEY, t); }
function clearToken() { localStorage.removeItem(TOKEN_KEY); }

async function api(path, opts = {}) {
  const headers = { "Content-Type": "application/json", ...(opts.headers || {}) };
  const token = getToken();
  if (token) headers["Authorization"] = "Bearer " + token;
  const res = await fetch(API + path, { ...opts, headers });
  return res.json();
}

// 导航栏：登录态显示"我的订单/退出"
function refreshNav() {
  const logged = !!getToken();
  document.getElementById("nav-me").style.display = logged ? "" : "none";
  document.getElementById("nav-login").style.display = logged ? "none" : "";
  document.getElementById("nav-register").style.display = logged ? "none" : "";
  document.getElementById("nav-logout").style.display = logged ? "" : "none";
}

document.addEventListener("DOMContentLoaded", refreshNav);

// 退出
document.getElementById("nav-logout")?.addEventListener("click", (e) => {
  e.preventDefault();
  clearToken();
  refreshNav();
  location.href = "/";
});

// ---------- 首页：加载商品 + 轮询库存 ----------
async function loadProduct() {
  const r = await api("/api/product/1");
  if (r.error) { document.getElementById("p-name").textContent = r.error; return; }
  const d = r.data;
  document.getElementById("p-name").textContent = d.name;
  document.getElementById("p-price").textContent = "¥" + d.price;
  document.getElementById("p-stock").textContent = "库存 " + d.stock;
  document.getElementById("p-source").textContent = "读源：" + (r.source || r.cache || "");
  // 库存 0 → 按钮置灰
  document.getElementById("btn-seckill").disabled = d.stock <= 0;
  show(`缓存 ${r.cache} · ${d.stock > 0 ? "还有货！" : "已抢完"}`);
}

async function loadStats() {
  const r = await api("/api/stats");
  if (r.error) return;
  document.getElementById("stats").textContent =
    `全站订单 ${r.orders} / 排队 ${r.queue} / 已抢 ${r.bought} / 读源 ${r.read_source}`;
}

function show(msg) { document.getElementById("result").textContent = msg; }

async function seckill() {
  const r = await api("/api/seckill", { method: "POST", body: JSON.stringify({}) });
  if (r.ok) show("🎯 " + r.msg);
  else {
    show("⚠️ " + r.error);          // 409 一人一单 / 401 未登录
    if (r.error && r.error.indexOf("登录") >= 0) setTimeout(() => location.href = "/login", 1200);
  }
}

// 页面就绪后：加载商品 + 每 1 秒轮询库存（看数字跳）
if (document.getElementById("product")) {
  loadProduct();
  loadStats();
  loadProducts();
  setInterval(loadProduct, 1000);
  setInterval(loadStats, 1000);
}

// ---------- 商品列表 ----------
async function loadProducts() {
  const r = await api("/api/products");
  if (r.error) return;
  const box = document.getElementById("products-list");
  const head = `<div class="muted" style="margin-bottom:6px;">列表缓存：${r.cache} · 读源：${r.source || "--"}</div>`;
  const rows = r.data.map(p =>
    `<div class="product mini">
       <div class="product-info">
         <h2>${p.name}</h2>
         <div class="muted">库存 ${p.stock}</div>
       </div>
       <div style="text-align:right">
         <div class="price">¥${p.price}</div>
         <button class="btn btn-primary btn-sm" onclick="addCart(${p.id})">加入购物车</button>
       </div>
     </div>`).join("");
  box.innerHTML = head + rows;
}

// ---------- 购物车 ----------
async function addCart(pid) {
  const r = await api("/api/cart/add", { method: "POST", body: JSON.stringify({ product_id: pid }) });
  if (r.ok) {
    show("🛒 " + r.msg + "（可在导航栏「购物车」查看）");
  } else {
    show("需要先登录：" + r.error);
    setTimeout(() => location.href = "/login", 1200);
  }
}

async function loadCart() {
  const r = await api("/api/cart");
  const table = document.getElementById("cart-table");
  const body = document.getElementById("cart-body");
  const totalBox = document.getElementById("cart-total");
  const btn = document.getElementById("btn-checkout");
  const empty = document.getElementById("cart-empty");
  if (r.error) { empty.textContent = "请先登录（" + r.error + "）"; return; }
  if (!r.items.length) {
    table.style.display = "none"; totalBox.textContent = ""; btn.style.display = "none";
    empty.textContent = "购物车是空的 —— 去首页把商品加进来";
    return;
  }
  empty.style.display = "none";
  table.style.display = "";
  body.innerHTML = r.items.map(it =>
    `<tr>
       <td>${it.name}</td><td>¥${it.price}</td>
       <td>${it.qty}</td><td>¥${it.subtotal}</td>
       <td><button class="btn btn-sm" onclick="checkout()">结算</button></td>
     </tr>`).join("");
  totalBox.textContent = "合计 ¥" + r.total;
  btn.style.display = "";
}

async function checkout() {
  const r = await api("/api/cart/checkout", { method: "POST", body: JSON.stringify({}) });
  if (r.ok) {
    document.getElementById("cart-msg").textContent = "✅ " + r.msg;
    loadCart(); loadStats(); loadProducts();
  } else {
    document.getElementById("cart-msg").textContent = "⚠️ " + r.error;
  }
}

// ---------- 登录 / 注册 ----------
async function doLogin(ev) {
  ev.preventDefault();
  const r = await api("/api/login", {
    method: "POST",
    body: JSON.stringify({ username: document.getElementById("username").value,
                           password: document.getElementById("password").value }),
  });
  if (r.ok) { setToken(r.token); refreshNav(); location.href = "/"; }
  else document.getElementById("err").textContent = r.error;
  return false;
}

async function doRegister(ev) {
  ev.preventDefault();
  const r = await api("/api/register", {
    method: "POST",
    body: JSON.stringify({ username: document.getElementById("username").value,
                           password: document.getElementById("password").value }),
  });
  if (r.ok) { setToken(r.token); refreshNav(); location.href = "/"; }
  else document.getElementById("err").textContent = r.error;
  return false;
}

// ---------- 我的订单 ----------
async function loadMe() {
  const r = await api("/api/me");
  const box = document.getElementById("me-box");
  const table = document.getElementById("orders-table");
  if (r.error) { box.textContent = "请先登录（" + r.error + "）"; return; }
  box.textContent = `👤 ${r.username}（uid=${r.uid}）`;
  if (!r.orders || !r.orders.length) { box.textContent += " —— 还没有订单"; return; }
  table.style.display = "";
  const body = document.getElementById("orders-body");
  body.innerHTML = r.orders.map(o =>
    `<tr><td>${o.name || "商品 #" + o.product_id}</td><td>¥${o.amount}</td><td>${o.created_at}</td></tr>`
  ).join("");
}

if (document.getElementById("me-box")) loadMe();
if (document.getElementById("cart-body")) loadCart();
