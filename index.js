// ═══════════════════════════════════════════════════════════════
//  WhatsApp Broadcast Bot — Single File Version
// ═══════════════════════════════════════════════════════════════

"use strict";

const { Telegraf, Markup }    = require("telegraf");
const { Client, LocalAuth }   = require("whatsapp-web.js");
const { readFileSync, existsSync, readdirSync, statSync } = require("fs");
const { join, sep }           = require("path");
const { execSync }            = require("child_process");
const http                    = require("http");
const https                   = require("https");
const os                      = require("os");

// ─── ENV CHECK ─────────────────────────────────────────────────
const TOKEN = process.env.TELEGRAM_BOT_TOKEN;
if (!TOKEN) throw new Error("❌ TELEGRAM_BOT_TOKEN set nahi hai!");

// Render par deploy ke baad apna Telegram user ID yahan set karo
// taaki startup aur connect/disconnect par notification mile
const OWNER_ID = process.env.OWNER_TELEGRAM_ID
  ? parseInt(process.env.OWNER_TELEGRAM_ID)
  : null;

const bot   = new Telegraf(TOKEN);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const MAX_GROUPS = 48;

// ═══════════════════════════════════════════════════════════════
//  SESSION
// ═══════════════════════════════════════════════════════════════
const sessions = new Map();

function getSession(userId) {
  if (!sessions.has(userId)) {
    sessions.set(userId, {
      state: "idle",
      delaySeconds: 3,
      repeatHours: 1,
      scheduleDays: null,
      broadcastActive: false,
      broadcastEndTime: null,
      broadcastCycles: 0,
      wa1Groups: [],
      wa2Groups: [],
      selectedWa1Ids: [],
      selectedWa2Ids: [],
      selectionMsgId: undefined,
    });
  }
  return sessions.get(userId);
}

function updateSession(userId, patch) {
  sessions.set(userId, { ...getSession(userId), ...patch });
}

// ═══════════════════════════════════════════════════════════════
//  SCHEDULER
// ═══════════════════════════════════════════════════════════════
const activeJobs = new Map();

function startSchedule(userId) {
  stopSchedule(userId);
  const flag = { stopped: false };
  activeJobs.set(userId, flag);
  return flag;
}

function stopSchedule(userId) {
  const existing = activeJobs.get(userId);
  if (existing) {
    existing.stopped = true;
    activeJobs.delete(userId);
  }
}

function isActive(userId) { return activeJobs.has(userId); }

// ═══════════════════════════════════════════════════════════════
//  SCRIPTS
// ═══════════════════════════════════════════════════════════════
function readScript(num) {
  const filePath = join(__dirname, "data", `script${num}.txt`);
  if (!existsSync(filePath)) return [];
  return readFileSync(filePath, "utf8")
    .split("\n").map((l) => l.trim()).filter((l) => l.length > 0);
}

function randomMessage(msgs) {
  if (!msgs.length) return "";
  return msgs[Math.floor(Math.random() * msgs.length)];
}

// ═══════════════════════════════════════════════════════════════
//  CHROME FINDER
// ═══════════════════════════════════════════════════════════════
function findChromium() {
  if (process.env.CHROMIUM_PATH && existsSync(process.env.CHROMIUM_PATH)) {
    console.log("[Chrome] CHROMIUM_PATH:", process.env.CHROMIUM_PATH);
    return process.env.CHROMIUM_PATH;
  }

  const cacheDirs = [
    process.env.PUPPETEER_CACHE_DIR,
    "/opt/render/project/src/.cache/puppeteer",
    join(os.homedir(), ".cache", "puppeteer"),
    join(process.cwd(), ".cache", "puppeteer"),
    "/root/.cache/puppeteer",
  ].filter(Boolean);

  for (const cacheDir of cacheDirs) {
    try {
      if (!existsSync(cacheDir)) continue;
      const chromeDir = join(cacheDir, "chrome");
      if (!existsSync(chromeDir)) continue;
      for (const platform of readdirSync(chromeDir)) {
        const pd = join(chromeDir, platform);
        if (!statSync(pd).isDirectory()) continue;
        for (const ver of readdirSync(pd)) {
          for (const c of [
            join(pd, ver, "chrome"),
            join(pd, ver, "chrome-linux", "chrome"),
            join(pd, ver, "chrome-linux64", "chrome"),
          ]) {
            if (existsSync(c)) { console.log("[Chrome] Mila:", c); return c; }
          }
        }
      }
    } catch {}
  }

  try {
    const p = eval("require")("puppeteer");
    const ep = p.executablePath();
    if (ep && existsSync(ep)) { console.log("[Chrome] puppeteer.executablePath:", ep); return ep; }
  } catch {}

  try {
    const f = execSync(
      "which google-chrome-stable || which google-chrome || which chromium-browser || which chromium 2>/dev/null",
      { encoding: "utf8" }
    ).trim();
    if (f && existsSync(f)) { console.log("[Chrome] System chromium:", f); return f; }
  } catch {}

  throw new Error(
    "Chrome nahi mila!\nRender Build Command:\n" +
    "npm install && PUPPETEER_CACHE_DIR=/opt/render/project/src/.cache/puppeteer npx puppeteer browsers install chrome\n" +
    "Env: PUPPETEER_CACHE_DIR = /opt/render/project/src/.cache/puppeteer"
  );
}

// ═══════════════════════════════════════════════════════════════
//  WHATSAPP MANAGER
// ═══════════════════════════════════════════════════════════════
const accounts = [
  { client: null, status: "disconnected", phoneNumber: "" },
  { client: null, status: "disconnected", phoneNumber: "" },
];

const pendingPairingCbs  = new Map();
const pendingReadyCbs    = new Map();
const connectTimeouts    = new Map();

function getStatus(i) { return accounts[i].status; }
function getPhone(i)  { return accounts[i].phoneNumber; }

// Owner ko notification bhejna
async function notifyOwner(text) {
  if (!OWNER_ID) return;
  try { await bot.telegram.sendMessage(OWNER_ID, text, { parse_mode: "Markdown" }); } catch {}
}

function createClient(index, phoneNumber) {
  let chromePath;
  try { chromePath = findChromium(); }
  catch (err) { throw err; }

  const client = new Client({
    authStrategy: new LocalAuth({ clientId: `wa-account-${index + 1}` }),
    authTimeoutMs: 0,   // ── timeout hatao
    qrMaxRetries: 0,    // ── infinite retries
    puppeteer: {
      headless: true,
      executablePath: chromePath,
      timeout: 0,
      args: [
        "--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage",
        "--disable-accelerated-2d-canvas", "--no-first-run", "--no-zygote",
        "--single-process", "--disable-gpu", "--disable-extensions",
        "--disable-background-networking", "--disable-background-timer-throttling",
        "--disable-backgrounding-occluded-windows", "--disable-breakpad",
        "--disable-client-side-phishing-detection",
        "--disable-component-extensions-with-background-pages",
        "--disable-default-apps", "--disable-features=TranslateUI",
        "--disable-hang-monitor", "--disable-ipc-flooding-protection",
        "--disable-popup-blocking", "--disable-prompt-on-repost",
        "--disable-renderer-backgrounding", "--disable-sync",
        "--force-color-profile=srgb", "--metrics-recording-only",
        "--safebrowsing-disable-auto-update",
      ],
    },
  });

  // ── QR → pairing code ──
  client.on("qr", async () => {
    try {
      console.log(`[WA${index + 1}] QR mila — pairing code request...`);
      const code = await Promise.race([
        client.requestPairingCode(phoneNumber),
        new Promise((_, rej) => setTimeout(() => rej(new Error("Pairing timeout 30s")), 30000)),
      ]);
      console.log(`[WA${index + 1}] Pairing code mila!`);
      const cb = pendingPairingCbs.get(index);
      if (cb) { pendingPairingCbs.delete(index); const t = connectTimeouts.get(index); if (t) { clearTimeout(t); connectTimeouts.delete(index); } await cb(code, null); }
    } catch (err) {
      console.error(`[WA${index + 1}] Pairing error:`, err.message);
      const cb = pendingPairingCbs.get(index);
      if (cb) { pendingPairingCbs.delete(index); const t = connectTimeouts.get(index); if (t) { clearTimeout(t); connectTimeouts.delete(index); } await cb(null, err); }
    }
  });

  // ── READY ──
  client.on("ready", async () => {
    accounts[index].status = "connected";
    console.log(`[WA${index + 1}] ✅ Connected! ${phoneNumber}`);

    // Pending callback (naya connect)
    const cb = pendingReadyCbs.get(index);
    if (cb) { pendingReadyCbs.delete(index); await cb(); }

    // Owner notification (restart ke baad auto-reconnect)
    await notifyOwner(`✅ *WA Account ${index + 1} Connected!*\n📱 \`${phoneNumber}\`\n\n_Main menu ke liye /menu bhejo_`);
  });

  client.on("authenticated", () => {
    console.log(`[WA${index + 1}] Authenticated ✔`);
  });

  client.on("disconnected", async (reason) => {
    accounts[index].status = "disconnected";
    console.log(`[WA${index + 1}] Disconnected:`, reason);
    await notifyOwner(`⚠️ *WA Account ${index + 1} Disconnect Ho Gaya!*\n📱 \`${phoneNumber}\`\nReason: ${reason}\n\nDobara connect karne ke liye /menu bhejo`);
  });

  client.on("auth_failure", async (msg) => {
    accounts[index].status = "disconnected";
    console.error(`[WA${index + 1}] Auth failure:`, msg);
    await notifyOwner(`❌ *WA Account ${index + 1} Auth Fail!*\n📱 \`${phoneNumber}\`\nDobara link karein.`);
  });

  return client;
}

async function connectAccount(index, phoneNumber) {
  const existing = accounts[index].client;
  if (existing) { try { await existing.destroy(); } catch {} }

  accounts[index].status = "connecting";
  accounts[index].phoneNumber = phoneNumber;

  const client = createClient(index, phoneNumber);
  accounts[index].client = client;

  // Background mein chalao — await nahi karo (warna 90s timeout se crash)
  client.initialize().catch((err) => {
    console.error(`[WA${index + 1}] Initialize error:`, err.message);
    if (accounts[index].status !== "connected") {
      accounts[index].status = "disconnected";
    }
  });
}

async function disconnectAccount(index) {
  const acc = accounts[index];
  if (acc.client) { try { await acc.client.destroy(); } catch {} acc.client = null; }
  acc.status = "disconnected";
  acc.phoneNumber = "";
}

async function getAllGroups(index) {
  const acc = accounts[index];
  if (!acc.client || acc.status !== "connected") return [];
  const chats = await acc.client.getChats();
  return chats.filter((c) => c.isGroup).map((c) => ({ id: c.id._serialized, name: c.name }));
}

async function sendMessageToGroup(index, groupId, message) {
  const acc = accounts[index];
  if (!acc.client || acc.status !== "connected") return false;
  try {
    const chat = await acc.client.getChatById(groupId);
    await chat.sendMessage(message);
    return true;
  } catch (err) {
    console.error(`[WA${index + 1}] Send error:`, err.message);
    return false;
  }
}

// ─── AUTO-RECONNECT on startup ──────────────────────────────────
// Agar pehle se LocalAuth session saved hai toh restart ke baad
// automatically reconnect karo — user ko dobara link nahi karna padega
async function autoReconnect() {
  for (let i = 0; i < 2; i++) {
    const authDir = join(process.cwd(), `.wwebjs_auth`, `session-wa-account-${i + 1}`);
    if (existsSync(authDir)) {
      console.log(`[AutoReconnect] WA${i + 1} ka session mila — reconnect kar raha hai...`);
      await notifyOwner(`🔄 *Bot Restart Hua — WA Account ${i + 1} Reconnect Ho Raha Hai...*\n_(Phone number saved session se load ho raha hai)_`);
      try {
        // Phone number session se pata nahi hota, placeholder use karo
        // ready event fire hoga aur wahan actual number update ho sakta hai
        accounts[i].phoneNumber = "saved-session";
        const client = createClient(i, "");
        accounts[i].client = client;
        client.initialize().catch((err) => {
          console.error(`[AutoReconnect] WA${i + 1} error:`, err.message);
          if (accounts[i].status !== "connected") accounts[i].status = "disconnected";
        });
      } catch (err) {
        console.error(`[AutoReconnect] WA${i + 1} failed:`, err.message);
      }
      await sleep(3000); // Dono accounts ek saath start hone se conflict na ho
    }
  }
}

// ═══════════════════════════════════════════════════════════════
//  TELEGRAM BOT — HELPERS
// ═══════════════════════════════════════════════════════════════
function statusEmoji(s) {
  return s === "connected" ? "✅" : s === "connecting" ? "⏳" : "❌";
}
function formatDuration(days) {
  if (days === null) return "Nonstop ♾️";
  return days === 1 ? "1 Din" : `${days} Din`;
}
function formatRepeat(hours) {
  if (hours < 1) return `${hours * 60} min`;
  if (hours === 1) return "1 Ghanta";
  if (hours < 24) return `${hours} Ghante`;
  return `${hours / 24} Din`;
}
function formatTimeLeft(endTime) {
  if (!endTime) return "Nonstop ♾️";
  const ms = endTime - Date.now();
  if (ms <= 0) return "Khatam";
  const h = Math.floor(ms / 3600000);
  const m = Math.floor((ms % 3600000) / 60000);
  return h >= 24 ? `${Math.floor(h / 24)}d ${h % 24}h baaki` : `${h}h ${m}m baaki`;
}

function mainMenu(userId) {
  const s1 = getStatus(0), s2 = getStatus(1);
  const p1 = getPhone(0) || "Connect nahi";
  const p2 = getPhone(1) || "Connect nahi";
  const active = userId ? isActive(userId) : false;
  const rows = [
    [Markup.button.callback(`${statusEmoji(s1)} WA Account 1 — ${p1}`, "menu_wa1")],
    [Markup.button.callback(`${statusEmoji(s2)} WA Account 2 — ${p2}`, "menu_wa2")],
    [Markup.button.callback("⏱️ Message Delay", "menu_delay"), Markup.button.callback("⏰ Schedule", "menu_schedule")],
  ];
  rows.push(active
    ? [Markup.button.callback("🛑 Broadcast BAND Karein", "stop_broadcast")]
    : [Markup.button.callback("🚀 Broadcast Shuru Karein", "menu_broadcast")]
  );
  rows.push([Markup.button.callback("📊 Status Dekhein", "menu_status")]);
  return Markup.inlineKeyboard(rows);
}

async function sendMainMenu(ctx, text) {
  await ctx.reply(
    text || "👋 *WhatsApp Broadcast Bot*\n\nMenu se option chunein:",
    { parse_mode: "Markdown", ...mainMenu(ctx.from?.id) }
  );
}

// ═══════════════════════════════════════════════════════════════
//  COMMANDS
// ═══════════════════════════════════════════════════════════════
bot.start(async (ctx) => sendMainMenu(ctx));
bot.command("menu", async (ctx) => sendMainMenu(ctx));

// ─── WA connect menu ───────────────────────────────────────────
async function handleConnectMenu(ctx, index) {
  const userId = ctx.from.id;
  const status = getStatus(index), phone = getPhone(index), acc = index + 1;
  if (status === "connected") {
    return ctx.reply(`📱 *WA Account ${acc}*\n✅ Connected: \`${phone}\``, {
      parse_mode: "Markdown",
      ...Markup.inlineKeyboard([
        [Markup.button.callback(`🔌 Logout Account ${acc}`, `logout_${index}`)],
        [Markup.button.callback("🔙 Main Menu", "back_menu")],
      ]),
    });
  }
  if (status === "connecting") {
    return ctx.reply("⏳ *Abhi connect ho raha hai...* Wait karein.", {
      parse_mode: "Markdown",
      ...Markup.inlineKeyboard([[Markup.button.callback("🔙 Main Menu", "back_menu")]]),
    });
  }
  updateSession(userId, { state: index === 0 ? "awaiting_phone1" : "awaiting_phone2" });
  await ctx.reply(
    `📱 *WA Account ${acc} Connect Karein*\n\nPhone number bhejein (country code ke saath):\nExample: \`919876543210\``,
    { parse_mode: "Markdown", ...Markup.inlineKeyboard([[Markup.button.callback("🔙 Main Menu", "back_menu")]]) }
  );
}

bot.action("menu_wa1", async (ctx) => { await ctx.answerCbQuery(); await handleConnectMenu(ctx, 0); });
bot.action("menu_wa2", async (ctx) => { await ctx.answerCbQuery(); await handleConnectMenu(ctx, 1); });

bot.action(/^logout_(\d)$/, async (ctx) => {
  await ctx.answerCbQuery("Logout ho raha hai...");
  const index = parseInt(ctx.match[1]);
  await ctx.editMessageText(`⏳ WA Account ${index + 1} logout ho raha hai...`);
  await disconnectAccount(index);
  await ctx.editMessageText(`✅ *WA Account ${index + 1} logout ho gaya!*`, { parse_mode: "Markdown" });
  await sleep(700);
  await sendMainMenu(ctx);
});

// ─── Delay ─────────────────────────────────────────────────────
bot.action("menu_delay", async (ctx) => {
  await ctx.answerCbQuery();
  const session = getSession(ctx.from.id);
  await ctx.reply(
    `⏱️ *Message Delay*\nCurrent: *${session.delaySeconds}s*\n\nHar group ke baad kitna wait?`,
    { parse_mode: "Markdown", ...Markup.inlineKeyboard([
      [Markup.button.callback("1s","delay_1"), Markup.button.callback("3s","delay_3"), Markup.button.callback("5s","delay_5"), Markup.button.callback("10s","delay_10"), Markup.button.callback("30s","delay_30")],
      [Markup.button.callback("🔙 Main Menu","back_menu")],
    ])}
  );
});
[1,3,5,10,30].forEach((d) => {
  bot.action(`delay_${d}`, async (ctx) => {
    await ctx.answerCbQuery();
    updateSession(ctx.from.id, { delaySeconds: d });
    await ctx.editMessageText(`✅ Delay: *${d}s*`, { parse_mode: "Markdown" });
    await sleep(500); await sendMainMenu(ctx);
  });
});

// ─── Schedule ──────────────────────────────────────────────────
bot.action("menu_schedule", async (ctx) => {
  await ctx.answerCbQuery();
  const s = getSession(ctx.from.id);
  await ctx.reply(
    `⏰ *Schedule*\n• Duration: *${formatDuration(s.scheduleDays)}*\n• Repeat: *Har ${formatRepeat(s.repeatHours)}*\n\nKitne din chalana hai:`,
    { parse_mode: "Markdown", ...Markup.inlineKeyboard([
      [Markup.button.callback("♾️ Nonstop","sch_days_0"), Markup.button.callback("1 Din","sch_days_1"), Markup.button.callback("3 Din","sch_days_3")],
      [Markup.button.callback("7 Din","sch_days_7"), Markup.button.callback("10 Din","sch_days_10"), Markup.button.callback("30 Din","sch_days_30")],
      [Markup.button.callback("🔙 Main Menu","back_menu")],
    ])}
  );
});
[0,1,3,7,10,30].forEach((d) => {
  bot.action(`sch_days_${d}`, async (ctx) => {
    await ctx.answerCbQuery();
    updateSession(ctx.from.id, { scheduleDays: d === 0 ? null : d });
    await ctx.editMessageText(
      `✅ Duration: *${formatDuration(d === 0 ? null : d)}*\n\nKitni baar repeat karna hai:`,
      { parse_mode: "Markdown", ...Markup.inlineKeyboard([
        [Markup.button.callback("30 min","sch_rep_0.5"), Markup.button.callback("1 Ghanta","sch_rep_1"), Markup.button.callback("2 Ghante","sch_rep_2")],
        [Markup.button.callback("6 Ghante","sch_rep_6"), Markup.button.callback("12 Ghante","sch_rep_12"), Markup.button.callback("24 Ghante","sch_rep_24")],
        [Markup.button.callback("🔙 Main Menu","back_menu")],
      ])}
    );
  });
});
[0.5,1,2,6,12,24].forEach((h) => {
  bot.action(`sch_rep_${h}`, async (ctx) => {
    await ctx.answerCbQuery();
    const s = getSession(ctx.from.id);
    updateSession(ctx.from.id, { repeatHours: h });
    await ctx.editMessageText(
      `✅ *Schedule Save!*\n⏰ Duration: *${formatDuration(s.scheduleDays)}*\n🔄 Repeat: *Har ${formatRepeat(h)}*`,
      { parse_mode: "Markdown" }
    );
    await sleep(600); await sendMainMenu(ctx);
  });
});

// ─── Status ────────────────────────────────────────────────────
bot.action("menu_status", async (ctx) => {
  await ctx.answerCbQuery();
  const userId = ctx.from.id;
  const s = getSession(userId);
  const sc1 = readScript(1), sc2 = readScript(2);
  await ctx.reply(
    `📊 *Bot Status*\n\n` +
    `📱 WA1: ${statusEmoji(getStatus(0))} ${getStatus(0).toUpperCase()}${getPhone(0) ? `\n  \`${getPhone(0)}\`` : ""}\n` +
    `📱 WA2: ${statusEmoji(getStatus(1))} ${getStatus(1).toUpperCase()}${getPhone(1) ? `\n  \`${getPhone(1)}\`` : ""}\n\n` +
    `📝 Script 1: ${sc1.length} msgs | Script 2: ${sc2.length} msgs\n` +
    `⏱️ Delay: ${s.delaySeconds}s | ⏰ ${formatDuration(s.scheduleDays)} | 🔄 ${formatRepeat(s.repeatHours)}\n` +
    `🔁 Cycles: ${s.broadcastCycles}\n` +
    `📡 ${isActive(userId) ? "🟢 Chal raha hai" : "🔴 Band hai"}` +
    (s.broadcastEndTime ? `\n⏳ ${formatTimeLeft(s.broadcastEndTime)}` : ""),
    { parse_mode: "Markdown", ...Markup.inlineKeyboard([[Markup.button.callback("🔙 Main Menu","back_menu")]]) }
  );
});

// ─── Stop ──────────────────────────────────────────────────────
bot.action("stop_broadcast", async (ctx) => {
  await ctx.answerCbQuery("Band ho raha hai...");
  const userId = ctx.from.id;
  stopSchedule(userId);
  updateSession(userId, { broadcastActive: false, broadcastEndTime: null });
  await ctx.reply("🛑 *Broadcast Band Ho Gaya!*", { parse_mode: "Markdown", ...mainMenu(userId) });
});

// ─── Broadcast start ───────────────────────────────────────────
bot.action("menu_broadcast", async (ctx) => {
  await ctx.answerCbQuery();
  const userId = ctx.from.id;
  const s1 = getStatus(0), s2 = getStatus(1);
  const sc1 = readScript(1), sc2 = readScript(2);

  if (s1 !== "connected" && s2 !== "connected") {
    return ctx.reply("❌ Koi WA account connected nahi!", Markup.inlineKeyboard([
      [Markup.button.callback("📱 WA 1","menu_wa1"), Markup.button.callback("📱 WA 2","menu_wa2")],
      [Markup.button.callback("🔙 Wapas","back_menu")],
    ]));
  }
  if (!sc1.length && !sc2.length) {
    return ctx.reply("❌ Scripts khali hain!\n`data/script1.txt` ya `data/script2.txt` mein messages add karein.",
      Markup.inlineKeyboard([[Markup.button.callback("🔙 Wapas","back_menu")]]));
  }

  await ctx.reply("⏳ Groups load ho rahe hain...");
  updateSession(userId, { selectionMsgId: undefined, broadcastCycles: 0 });

  if (s1 === "connected" && sc1.length) {
    const groups = await getAllGroups(0);
    updateSession(userId, { state: "selecting_wa1", wa1Groups: groups, selectedWa1Ids: groups.map((g) => g.id) });
    await showGroupSelection(ctx, 1, userId);
  } else {
    const groups = await getAllGroups(1);
    updateSession(userId, { state: "selecting_wa2", wa2Groups: groups, selectedWa2Ids: groups.map((g) => g.id) });
    await showGroupSelection(ctx, 2, userId);
  }
});

// ─── Group selection ───────────────────────────────────────────
function groupKeyboard(waIndex, groups, selectedIds) {
  const sel = new Set(selectedIds);
  const shown = groups.slice(0, MAX_GROUPS);
  const allSel = shown.every((g) => sel.has(g.id));
  const rows = [];
  rows.push([Markup.button.callback(allSel ? "◻️ Sab Deselect" : "✅ Sab Select", allSel ? `da${waIndex}` : `sa${waIndex}`)]);
  shown.forEach((g, i) => rows.push([Markup.button.callback(`${sel.has(g.id) ? "✅" : "◻️"} ${g.name.slice(0,28)}`, `tg${waIndex}_${i}`)]));
  rows.push([Markup.button.callback(`🚀 Confirm — ${selectedIds.length} groups`, `confirm_wa${waIndex}`)]);
  rows.push([Markup.button.callback("🔙 Main Menu","back_menu")]);
  return Markup.inlineKeyboard(rows);
}

async function showGroupSelection(ctx, waIndex, userId) {
  const s = getSession(userId);
  const groups = waIndex === 1 ? s.wa1Groups : s.wa2Groups;
  const selectedIds = waIndex === 1 ? s.selectedWa1Ids : s.selectedWa2Ids;
  const text = `📱 *WA Account ${waIndex} (${getPhone(waIndex-1)||"—"})*\nGroups: *${groups.length}* | Selected: *${selectedIds.length}*\n\nSelect karein:`;
  const kb = groupKeyboard(waIndex, groups, selectedIds);
  if (s.selectionMsgId) {
    try {
      await ctx.telegram.editMessageText(ctx.chat.id, s.selectionMsgId, undefined, text, { parse_mode:"Markdown", reply_markup: kb.reply_markup });
      return;
    } catch {}
  }
  const sent = await ctx.reply(text, { parse_mode:"Markdown", ...kb });
  updateSession(userId, { selectionMsgId: sent.message_id });
}

// WA1 group toggles
bot.action(/^tg1_(\d+)$/, async (ctx) => {
  await ctx.answerCbQuery();
  const uid = ctx.from.id, s = getSession(uid), g = s.wa1Groups[+ctx.match[1]];
  if (!g) return;
  const sel = new Set(s.selectedWa1Ids);
  sel.has(g.id) ? sel.delete(g.id) : sel.add(g.id);
  updateSession(uid, { selectedWa1Ids: [...sel] });
  await showGroupSelection(ctx, 1, uid);
});
bot.action("sa1", async (ctx) => { await ctx.answerCbQuery(); const s=getSession(ctx.from.id); updateSession(ctx.from.id,{selectedWa1Ids:s.wa1Groups.slice(0,MAX_GROUPS).map(g=>g.id)}); await showGroupSelection(ctx,1,ctx.from.id); });
bot.action("da1", async (ctx) => { await ctx.answerCbQuery(); updateSession(ctx.from.id,{selectedWa1Ids:[]}); await showGroupSelection(ctx,1,ctx.from.id); });

// WA2 group toggles
bot.action(/^tg2_(\d+)$/, async (ctx) => {
  await ctx.answerCbQuery();
  const uid = ctx.from.id, s = getSession(uid), g = s.wa2Groups[+ctx.match[1]];
  if (!g) return;
  const sel = new Set(s.selectedWa2Ids);
  sel.has(g.id) ? sel.delete(g.id) : sel.add(g.id);
  updateSession(uid, { selectedWa2Ids: [...sel] });
  await showGroupSelection(ctx, 2, uid);
});
bot.action("sa2", async (ctx) => { await ctx.answerCbQuery(); const s=getSession(ctx.from.id); updateSession(ctx.from.id,{selectedWa2Ids:s.wa2Groups.slice(0,MAX_GROUPS).map(g=>g.id)}); await showGroupSelection(ctx,2,ctx.from.id); });
bot.action("da2", async (ctx) => { await ctx.answerCbQuery(); updateSession(ctx.from.id,{selectedWa2Ids:[]}); await showGroupSelection(ctx,2,ctx.from.id); });

// Confirm WA1
bot.action("confirm_wa1", async (ctx) => {
  const uid = ctx.from.id, s = getSession(uid);
  if (!s.selectedWa1Ids.length) return ctx.answerCbQuery("⚠️ Kam se kam 1 group select karein!", { show_alert:true });
  await ctx.answerCbQuery();
  const sc2 = readScript(2);
  if (getStatus(1) === "connected" && sc2.length) {
    const groups = await getAllGroups(1);
    updateSession(uid, { state:"selecting_wa2", wa2Groups:groups, selectedWa2Ids:groups.map(g=>g.id), selectionMsgId:undefined });
    await ctx.reply("✅ WA1 confirmed!\n\nAb WA2 ke groups chunein:");
    await showGroupSelection(ctx, 2, uid);
  } else {
    await launchBroadcastLoop(ctx, uid);
  }
});

// Confirm WA2
bot.action("confirm_wa2", async (ctx) => {
  const uid = ctx.from.id, s = getSession(uid);
  if (!s.selectedWa2Ids.length) return ctx.answerCbQuery("⚠️ Kam se kam 1 group select karein!", { show_alert:true });
  await ctx.answerCbQuery();
  await launchBroadcastLoop(ctx, uid);
});

// ─── Broadcast loop ────────────────────────────────────────────
async function launchBroadcastLoop(ctx, userId) {
  const s = getSession(userId);
  const { scheduleDays, repeatHours, selectedWa1Ids, selectedWa2Ids } = s;
  const endTime = scheduleDays ? Date.now() + scheduleDays * 86400000 : null;
  updateSession(userId, { broadcastActive:true, broadcastEndTime:endTime, broadcastCycles:0, state:"idle" });
  const flag = startSchedule(userId);
  const chatId = ctx.chat.id;
  const schText = scheduleDays === null
    ? `♾️ Nonstop — Har *${formatRepeat(repeatHours)}* mein`
    : `📅 *${scheduleDays} din* — Har *${formatRepeat(repeatHours)}*\n⏳ Khatam: ${new Date(endTime).toLocaleString("en-IN")}`;

  await ctx.reply(`🚀 *Broadcast Shuru!*\n\n${schText}\n\n_🛑 Band karne ke liye button dabao._`,
    { parse_mode:"Markdown", ...mainMenu(userId) });

  const runLoop = async () => {
    while (!flag.stopped) {
      if (endTime && Date.now() >= endTime) {
        stopSchedule(userId); updateSession(userId, { broadcastActive:false, broadcastEndTime:null });
        try { await bot.telegram.sendMessage(chatId, `✅ *Schedule Complete!*\n🔁 Cycles: *${getSession(userId).broadcastCycles}*`, { parse_mode:"Markdown", ...mainMenu(userId) }); } catch {}
        break;
      }
      const cycleNum = getSession(userId).broadcastCycles + 1;
      const sc1 = readScript(1), sc2 = readScript(2);
      const total = selectedWa1Ids.length + selectedWa2Ids.length;
      let sent = 0, failed = 0;

      const buildStatus = (extra="⏳ Chal raha hai...") => {
        const ss = getSession(userId);
        return `📊 *Cycle #${cycleNum}*\n━━━━━━━━━━━━\n📱 WA1: \`${getPhone(0)||"—"}\`\n📱 WA2: \`${getPhone(1)||"—"}\`\n\n📍 Groups: ${total} | 📤 Sent: ${sent} | ❌ Failed: ${failed}\n🔁 Cycles: ${ss.broadcastCycles} | ⏳ ${formatTimeLeft(endTime)}\n\n${extra}`;
      };

      let statusMsgId;
      try { const m = await bot.telegram.sendMessage(chatId, buildStatus(), {parse_mode:"Markdown"}); statusMsgId = m.message_id; } catch {}
      const refresh = async (extra) => {
        if (!statusMsgId) return;
        try { await bot.telegram.editMessageText(chatId, statusMsgId, undefined, buildStatus(extra), {parse_mode:"Markdown"}); } catch {}
      };

      if (!flag.stopped && getStatus(0)==="connected" && sc1.length) {
        for (const gId of selectedWa1Ids) {
          if (flag.stopped) break;
          const g = getSession(userId).wa1Groups.find(x=>x.id===gId);
          const ok = await sendMessageToGroup(0, gId, randomMessage(sc1));
          ok ? sent++ : failed++;
          await refresh(`⏳ WA1 → _${g?.name??gId}_`);
          await sleep(getSession(userId).delaySeconds * 1000);
        }
      }
      if (!flag.stopped && getStatus(1)==="connected" && sc2.length) {
        for (const gId of selectedWa2Ids) {
          if (flag.stopped) break;
          const g = getSession(userId).wa2Groups.find(x=>x.id===gId);
          const ok = await sendMessageToGroup(1, gId, randomMessage(sc2));
          ok ? sent++ : failed++;
          await refresh(`⏳ WA2 → _${g?.name??gId}_`);
          await sleep(getSession(userId).delaySeconds * 1000);
        }
      }
      if (flag.stopped) break;

      updateSession(userId, { broadcastCycles: getSession(userId).broadcastCycles + 1 });
      await refresh(`✅ Cycle #${cycleNum} complete!`);
      const waitMs = repeatHours * 3600000;
      try { await bot.telegram.sendMessage(chatId, `✅ *Cycle #${cycleNum} Complete!*\n📤 ${sent} | ❌ ${failed}\n\n⏰ Agla: ${new Date(Date.now()+waitMs).toLocaleTimeString("en-IN")}`, {parse_mode:"Markdown"}); } catch {}

      const waitUntil = Date.now() + waitMs;
      while (!flag.stopped && Date.now() < waitUntil) await sleep(30000);
    }
  };

  runLoop().catch((err) => console.error("[BroadcastLoop]", err));
}

// ─── Back ──────────────────────────────────────────────────────
bot.action("back_menu", async (ctx) => {
  await ctx.answerCbQuery();
  updateSession(ctx.from.id, { state:"idle", selectionMsgId:undefined });
  await ctx.reply("🏠 Main Menu:", mainMenu(ctx.from.id));
});

// ─── Text (phone number) ───────────────────────────────────────
bot.on("text", async (ctx) => {
  const userId = ctx.from.id;
  const session = getSession(userId);
  const text = ctx.message.text.trim();
  if (text.startsWith("/")) return;

  if (session.state === "awaiting_phone1" || session.state === "awaiting_phone2") {
    const index = session.state === "awaiting_phone1" ? 0 : 1;
    const phone = text.replace(/[^0-9]/g, "");
    if (phone.length < 10) {
      return ctx.reply("❌ Invalid number.\nExample: `919876543210`", {
        parse_mode: "Markdown",
        ...Markup.inlineKeyboard([[Markup.button.callback("🔙 Wapas","back_menu")]]),
      });
    }
    updateSession(userId, { state: "idle" });
    await ctx.reply(
      `⏳ *WA Account ${index+1}* ke liye pairing code aa raha hai...\n_(Render par 1-2 minute lag sakte hain — please wait karein)_`,
      { parse_mode: "Markdown" }
    );

    // Pairing code callback
    pendingPairingCbs.set(index, async (code, err) => {
      if (err || !code) {
        await ctx.reply(
          `❌ *Pairing code nahi aaya — Account ${index+1}*\n\nError: \`${err?.message||"Unknown"}\`\n\nPossible fix:\n• Phone number check karein\n• Dobara try karein`,
          { parse_mode:"Markdown", ...Markup.inlineKeyboard([[Markup.button.callback("🔙 Menu","back_menu")]]) }
        );
        return;
      }
      const fmt = code.match(/.{1,4}/g)?.join("-") || code;
      await ctx.reply(
        `🔑 *Pairing Code — Account ${index+1}*\n\n\`${fmt}\`\n\n*Steps:*\n1. WhatsApp → *Settings → Linked Devices*\n2. *Link a Device → Link with phone number*\n3. Yeh code enter karein\n\n⏳ Link hone ka wait ho raha hai... (1-2 min)`,
        { parse_mode:"Markdown", ...Markup.inlineKeyboard([[Markup.button.callback("🔙 Main Menu","back_menu")]]) }
      );
    });

    // Ready callback
    pendingReadyCbs.set(index, async () => {
      await ctx.reply(
        `✅ *WA Account ${index+1} Connected!*\n📱 \`${phone}\``,
        { parse_mode:"Markdown", ...mainMenu(userId) }
      );
    });

    // 3 minute overall timeout
    const t = setTimeout(async () => {
      if (pendingPairingCbs.has(index)) {
        pendingPairingCbs.delete(index); pendingReadyCbs.delete(index); connectTimeouts.delete(index);
        try {
          await ctx.reply(
            `⏰ *Timeout — Account ${index+1}*\n\nPairing code 3 minute mein nahi aaya.\n\nRender Build Command check karein:\n\`npm install && PUPPETEER_CACHE_DIR=/opt/render/project/src/.cache/puppeteer npx puppeteer browsers install chrome\`\n\nDobara try karein.`,
            { parse_mode:"Markdown", ...Markup.inlineKeyboard([[Markup.button.callback("🔙 Menu","back_menu")]]) }
          );
        } catch {}
      }
    }, 180000);
    connectTimeouts.set(index, t);

    try {
      await connectAccount(index, phone);
    } catch (err) {
      clearTimeout(t); connectTimeouts.delete(index);
      pendingPairingCbs.delete(index); pendingReadyCbs.delete(index);
      await ctx.reply(
        `❌ *Error — Account ${index+1}*\n\`${err.message}\``,
        { parse_mode:"Markdown", ...Markup.inlineKeyboard([[Markup.button.callback("🔙 Wapas","back_menu")]]) }
      );
    }
    return;
  }

  await sendMainMenu(ctx, "👇 Menu se chunein:");
});

bot.catch((err) => console.error("[Bot Error]", err));

// ═══════════════════════════════════════════════════════════════
//  HTTP SERVER (Render keep-alive)
// ═══════════════════════════════════════════════════════════════
const express = require("express");
const app = express();
const PORT = process.env.PORT || 3000;

app.get("/", (_req, res) => res.send(`<html><body style="font-family:sans-serif;text-align:center;padding:50px"><h2>✅ WA Broadcast Bot</h2><p>🟢 Chal raha hai</p></body></html>`));
app.get("/health", (_req, res) => res.json({ status:"ok", uptime:Math.floor(process.uptime())+"s", wa1:getStatus(0), wa2:getStatus(1), ts:new Date().toISOString() }));
app.listen(PORT, () => console.log(`🌐 Web server — port ${PORT}`));

// Self-ping
function selfPing() {
  const url = process.env.RENDER_EXTERNAL_URL || process.env.SELF_URL;
  if (!url) return;
  const fullUrl = url.startsWith("https") ? url : `https://${url}`;
  (fullUrl.startsWith("https") ? https : http).get(`${fullUrl}/health`, (r) => {
    console.log(`[Ping] ✅ ${r.statusCode} — ${new Date().toLocaleTimeString()}`);
  }).on("error", (e) => console.error("[Ping] ❌", e.message));
}
setTimeout(() => { selfPing(); setInterval(selfPing, 120000); }, 60000);

// ═══════════════════════════════════════════════════════════════
//  LAUNCH
// ═══════════════════════════════════════════════════════════════
bot.launch({ dropPendingUpdates: true }).then(async () => {
  console.log("✅ Bot chal raha hai!");
  // Pehle se saved sessions auto-reconnect karo
  await autoReconnect();
  if (OWNER_ID) {
    await notifyOwner("🤖 *Bot Start Ho Gaya!*\n\nWhatsApp connect karne ke liye /menu bhejo.");
  }
});

process.once("SIGINT",  () => bot.stop("SIGINT"));
process.once("SIGTERM", () => bot.stop("SIGTERM"));
