/**
 * WhatsApp Broadcast Bot v5
 * - 10 WhatsApp accounts support
 * - MongoDB persistence (broadcasts survive restarts)
 * - Conversation mode (looks like 2 people chatting)
 * - Owner-only access
 * - Render.com ready
 */

const { Telegraf, Markup } = require("telegraf");
const { connectDB } = require("./src/db");
const { ActiveBroadcast } = require("./src/models");
const { getSession, updateSession, MAX_ACCOUNTS } = require("./src/session");
const { readScript, randomMessage } = require("./src/scripts");
const { startSchedule, stopSchedule, isActive } = require("./src/scheduler");
const {
  setCallbacks, getStatus, getPhone, getAllStatuses, getConnectedCount,
  connectAccount, disconnectAccount, getAllGroups, sendMessageToGroup,
  reconnectSavedAccounts,
} = require("./src/whatsapp-manager");
const express = require("express");
const http = require("http");
const https = require("https");

// ─── Env ───────────────────────────────────────────────────────────────
const TOKEN = process.env.TELEGRAM_BOT_TOKEN;
if (!TOKEN) { console.error("❌ TELEGRAM_BOT_TOKEN not set!"); process.exit(1); }
const OWNER_ID = parseInt(process.env.OWNER_ID || "0", 10);
if (!OWNER_ID) console.warn("⚠️  OWNER_ID not set — anyone can use this bot!");

const bot = new Telegraf(TOKEN);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// ─── Owner guard ────────────────────────────────────────────────────────
bot.use(async (ctx, next) => {
  if (OWNER_ID && ctx.from?.id !== OWNER_ID) {
    if (ctx.callbackQuery) await ctx.answerCbQuery("❌ Unauthorized.", { show_alert: true }).catch(() => {});
    else await ctx.reply("❌ Yeh bot sirf owner ke liye hai.").catch(() => {});
    return;
  }
  return next();
});

// ─── Pairing callbacks ─────────────────────────────────────────────────
const pendingPairingCbs = new Map();
const pendingReadyCbs = new Map();

setCallbacks({
  onPairingCode: async (index, code) => {
    const cb = pendingPairingCbs.get(index);
    if (cb) { pendingPairingCbs.delete(index); await cb(code); }
  },
  onReady: async (index) => {
    const cb = pendingReadyCbs.get(index);
    if (cb) { pendingReadyCbs.delete(index); await cb(); }
  },
  onDisconnected: async (index) => {
    console.log(`[Bot] WA${index + 1} logged out`);
  },
});

// ─── Formatters ────────────────────────────────────────────────────────
const se = (s) => s === "connected" ? "✅" : s === "connecting" ? "⏳" : "❌";
const fmtDays = (d) => d === null ? "Nonstop ♾️" : d === 1 ? "1 Din" : `${d} Din`;
const fmtHours = (h) => h < 1 ? `${h * 60} min` : h < 24 ? `${h} Ghante` : `${h / 24} Din`;
const fmtLeft = (e) => {
  if (!e) return "Nonstop ♾️";
  const ms = e - Date.now();
  if (ms <= 0) return "Khatam";
  const h = Math.floor(ms / 3600000), m = Math.floor((ms % 3600000) / 60000);
  return h >= 24 ? `${Math.floor(h / 24)}d ${h % 24}h baaki` : `${h}h ${m}m baaki`;
};

// ─── Menus ─────────────────────────────────────────────────────────────
function mainMenu(userId) {
  const n = getConnectedCount();
  const active = isActive(userId);
  const s = getSession(userId);
  return Markup.inlineKeyboard([
    [Markup.button.callback(`📱 Accounts (${n}/${MAX_ACCOUNTS} connected)`, "menu_accounts")],
    [Markup.button.callback("⏱️ Delay", "menu_delay"), Markup.button.callback("⏰ Schedule", "menu_schedule")],
    [Markup.button.callback(s.conversationMode ? "💬 Mode: Conversation ✅" : "📢 Mode: Normal", "toggle_mode")],
    [Markup.button.callback(active ? "🛑 Broadcast Band Karein" : "🚀 Broadcast Shuru Karein", active ? "stop_broadcast" : "menu_broadcast")],
    [Markup.button.callback("📊 Status", "menu_status")],
  ]);
}

async function sendMainMenu(ctx, text) {
  await ctx.reply(
    text || "👋 *WhatsApp Broadcast Bot v5*\n\nMenu se option chunein:",
    { parse_mode: "Markdown", ...mainMenu(ctx.from?.id) },
  );
}

function accountsKeyboard() {
  const rows = [];
  for (let i = 0; i < MAX_ACCOUNTS; i += 2) {
    const row = [];
    for (let j = i; j < Math.min(i + 2, MAX_ACCOUNTS); j++) {
      const s = getStatus(j), p = getPhone(j);
      const label = s === "connected" ? `✅ ${j+1} — ${p.slice(-5)}`
        : s === "connecting" ? `⏳ ${j+1} — wait...`
        : `❌ ${j+1} — Connect`;
      row.push(Markup.button.callback(label, `acc_${j}`));
    }
    rows.push(row);
  }
  rows.push([Markup.button.callback("🔙 Main Menu", "back_menu")]);
  return Markup.inlineKeyboard(rows);
}

async function showAccountsMenu(ctx) {
  const n = getConnectedCount();
  const text = `📱 *WhatsApp Accounts*\n${n}/${MAX_ACCOUNTS} connected\n\nAccount chunein:`;
  try { await ctx.editMessageText(text, { parse_mode: "Markdown", reply_markup: accountsKeyboard().reply_markup }); }
  catch { await ctx.reply(text, { parse_mode: "Markdown", ...accountsKeyboard() }); }
}

// ─── Commands ──────────────────────────────────────────────────────────
bot.start(async (ctx) => sendMainMenu(ctx));
bot.command("menu", async (ctx) => sendMainMenu(ctx));
bot.command("status", async (ctx) => {
  await ctx.reply(
    `📊 *Status*\n\n` +
    getAllStatuses().map((a) => `${se(a.status)} Acc${a.index+1}${a.phone ? ` — \`${a.phone}\`` : ""}`).join("\n"),
    { parse_mode: "Markdown", ...mainMenu(ctx.from.id) },
  );
});

// ─── Account actions ───────────────────────────────────────────────────
bot.action("menu_accounts", async (ctx) => { await ctx.answerCbQuery(); await showAccountsMenu(ctx); });

bot.action(/^acc_(\d+)$/, async (ctx) => {
  await ctx.answerCbQuery();
  const idx = parseInt(ctx.match[1]);
  const status = getStatus(idx), phone = getPhone(idx), n = idx + 1;

  if (status === "connected") {
    await ctx.reply(
      `📱 *WA Account ${n}*\n✅ Connected: \`${phone}\`\n\nLogout karna hai?`,
      { parse_mode: "Markdown", ...Markup.inlineKeyboard([
        [Markup.button.callback("🔌 Logout", `logout_${idx}`)],
        [Markup.button.callback("🔙 Accounts", "menu_accounts")],
      ])},
    );
  } else if (status === "connecting") {
    await ctx.reply(
      `⏳ *WA Account ${n}* connect ho raha hai...\nReset karna hai?`,
      { parse_mode: "Markdown", ...Markup.inlineKeyboard([
        [Markup.button.callback("🔄 Reset", `reset_${idx}`)],
        [Markup.button.callback("🔙 Accounts", "menu_accounts")],
      ])},
    );
  } else {
    updateSession(ctx.from.id, { awaitingPhoneForIndex: idx });
    await ctx.reply(
      `📱 *WA Account ${n} Connect Karein*\n\n` +
      `Phone number dalein (country code ke saath):\nExample: \`919876543210\`\n\n` +
      `_Code 15-30 sec mein aayega_\n⚠️ *Code 60 sec mein expire hota hai — jaldi enter karein!*`,
      { parse_mode: "Markdown", ...Markup.inlineKeyboard([[Markup.button.callback("🔙 Accounts", "menu_accounts")]])},
    );
  }
});

bot.action(/^logout_(\d+)$/, async (ctx) => {
  await ctx.answerCbQuery("Logout ho raha hai...");
  const idx = parseInt(ctx.match[1]);
  await ctx.editMessageText(`⏳ WA Account ${idx+1} logout ho raha hai...`);
  await disconnectAccount(idx);
  await ctx.editMessageText(`✅ *WA Account ${idx+1} logout ho gaya!*`, { parse_mode: "Markdown" });
  await sleep(600);
  await showAccountsMenu(ctx);
});

bot.action(/^reset_(\d+)$/, async (ctx) => {
  await ctx.answerCbQuery("Reset ho raha hai...");
  const idx = parseInt(ctx.match[1]);
  await disconnectAccount(idx);
  await ctx.editMessageText(`✅ *WA Account ${idx+1} reset ho gaya!*\n\nAb number dalein:`, { parse_mode: "Markdown" });
  updateSession(ctx.from.id, { awaitingPhoneForIndex: idx });
  await ctx.reply(
    `📱 Number dalein (example: \`919876543210\`):`,
    { parse_mode: "Markdown", ...Markup.inlineKeyboard([[Markup.button.callback("🔙 Accounts", "menu_accounts")]])},
  );
});

// ─── Toggle mode ────────────────────────────────────────────────────────
bot.action("toggle_mode", async (ctx) => {
  await ctx.answerCbQuery();
  const userId = ctx.from.id;
  const newMode = !getSession(userId).conversationMode;
  updateSession(userId, { conversationMode: newMode });
  await ctx.reply(
    newMode
      ? `💬 *Conversation Mode ON*\n\nSame group mein WA pairs ek ke baad ek message bhejenge — jaise 2 log baat kar rahe ho.`
      : `📢 *Normal Mode ON*\n\nHar account apne groups mein alag message bhejega.`,
    { parse_mode: "Markdown", ...mainMenu(userId) },
  );
});

// ─── Delay ─────────────────────────────────────────────────────────────
bot.action("menu_delay", async (ctx) => {
  await ctx.answerCbQuery();
  const s = getSession(ctx.from.id);
  await ctx.reply(
    `⏱️ *Message Delay*\nCurrent: *${s.delaySeconds}s*\n\nHar group ke baad kitna wait karein?`,
    { parse_mode: "Markdown", ...Markup.inlineKeyboard([
      [[3,5,10,15,30].map((d) => Markup.button.callback(`${d}s`, `delay_${d}`))],
      [Markup.button.callback("🔙 Main Menu", "back_menu")],
    ])},
  );
});
[3, 5, 10, 15, 30].forEach((d) => {
  bot.action(`delay_${d}`, async (ctx) => {
    await ctx.answerCbQuery();
    updateSession(ctx.from.id, { delaySeconds: d });
    await ctx.editMessageText(`✅ Delay: *${d}s*`, { parse_mode: "Markdown" });
    await sleep(400);
    await sendMainMenu(ctx);
  });
});

// ─── Schedule ──────────────────────────────────────────────────────────
bot.action("menu_schedule", async (ctx) => {
  await ctx.answerCbQuery();
  const s = getSession(ctx.from.id);
  await ctx.reply(
    `⏰ *Schedule*\n\nCurrent:\n• Duration: *${fmtDays(s.scheduleDays)}*\n• Repeat: *Har ${fmtHours(s.repeatHours)}*\n\nKitne din chalana hai?`,
    { parse_mode: "Markdown", ...Markup.inlineKeyboard([
      [Markup.button.callback("♾️ Nonstop","sd_0"), Markup.button.callback("1 Din","sd_1"), Markup.button.callback("3 Din","sd_3")],
      [Markup.button.callback("7 Din","sd_7"), Markup.button.callback("15 Din","sd_15"), Markup.button.callback("30 Din","sd_30")],
      [Markup.button.callback("🔙 Main Menu","back_menu")],
    ])},
  );
});
[0,1,3,7,15,30].forEach((d) => {
  bot.action(`sd_${d}`, async (ctx) => {
    await ctx.answerCbQuery();
    const days = d === 0 ? null : d;
    updateSession(ctx.from.id, { scheduleDays: days });
    await ctx.editMessageText(
      `✅ Duration: *${fmtDays(days)}*\n\nRepeat interval chunein:`,
      { parse_mode: "Markdown", ...Markup.inlineKeyboard([
        [Markup.button.callback("30 min","sr_0.5"), Markup.button.callback("1 Ghanta","sr_1"), Markup.button.callback("2 Ghante","sr_2")],
        [Markup.button.callback("6 Ghante","sr_6"), Markup.button.callback("12 Ghante","sr_12"), Markup.button.callback("24 Ghante","sr_24")],
        [Markup.button.callback("🔙 Main Menu","back_menu")],
      ])},
    );
  });
});
[0.5,1,2,6,12,24].forEach((h) => {
  bot.action(`sr_${h}`, async (ctx) => {
    await ctx.answerCbQuery();
    const s = getSession(ctx.from.id);
    updateSession(ctx.from.id, { repeatHours: h });
    await ctx.editMessageText(
      `✅ *Schedule Saved!*\n\n⏰ Duration: *${fmtDays(s.scheduleDays)}*\n🔄 Repeat: *Har ${fmtHours(h)}*`,
      { parse_mode: "Markdown" },
    );
    await sleep(500);
    await sendMainMenu(ctx);
  });
});

// ─── Status ─────────────────────────────────────────────────────────────
bot.action("menu_status", async (ctx) => {
  await ctx.answerCbQuery();
  const userId = ctx.from.id;
  const s = getSession(userId);
  const statuses = getAllStatuses();
  const waLines = statuses.map((a) =>
    `${se(a.status)} Acc${a.index+1}${a.phone ? ` — \`${a.phone}\`` : " — Disconnected"}`
  ).join("\n");

  let scriptInfo = "";
  for (let i = 1; i <= MAX_ACCOUNTS; i++) {
    const msgs = readScript(i);
    if (msgs.length > 0) scriptInfo += `  Script${i}: ${msgs.length} messages\n`;
  }

  await ctx.reply(
    `📊 *Status*\n\n*WhatsApp:*\n${waLines}\n\n` +
    (scriptInfo ? `*Scripts:*\n${scriptInfo}\n` : "") +
    `*💬 Mode:* ${s.conversationMode ? "Conversation" : "Normal"}\n` +
    `*⏱️ Delay:* ${s.delaySeconds}s\n` +
    `*⏰ Duration:* ${fmtDays(s.scheduleDays)}\n` +
    `*🔄 Repeat:* Har ${fmtHours(s.repeatHours)}\n` +
    `*📡 Broadcast:* ${isActive(userId) ? "🟢 Chal raha hai" : "🔴 Band hai"}`,
    { parse_mode: "Markdown", ...Markup.inlineKeyboard([[Markup.button.callback("🔙 Main Menu","back_menu")]])},
  );
});

// ─── Stop broadcast ────────────────────────────────────────────────────
bot.action("stop_broadcast", async (ctx) => {
  await ctx.answerCbQuery("Band ho raha hai...");
  const userId = ctx.from.id;
  stopSchedule(userId);
  await ActiveBroadcast.findOneAndUpdate({ userId }, { active: false }).catch(() => {});
  await ctx.reply("🛑 *Broadcast Band Ho Gaya!*", { parse_mode: "Markdown", ...mainMenu(userId) });
});

// ─── Broadcast — account selection ─────────────────────────────────────
bot.action("menu_broadcast", async (ctx) => {
  await ctx.answerCbQuery();
  const userId = ctx.from.id;
  const connected = getAllStatuses().filter((a) => a.status === "connected");

  if (!connected.length) {
    await ctx.reply("❌ Koi account connected nahi! Pehle ek account connect karein.",
      Markup.inlineKeyboard([[Markup.button.callback("📱 Accounts","menu_accounts"), Markup.button.callback("🔙 Wapas","back_menu")]]));
    return;
  }

  const hasAnyScript = connected.some((a) => readScript(a.index + 1).length > 0);
  if (!hasAnyScript) {
    await ctx.reply("❌ Kisi bhi account ka script nahi hai!\n`data/script1.txt` se `data/script10.txt` mein messages add karein.",
      Markup.inlineKeyboard([[Markup.button.callback("🔙 Wapas","back_menu")]]));
    return;
  }

  updateSession(userId, {
    selectedAccountIndices: connected.map((a) => a.index),
    selectionMsgId: undefined,
  });
  await showAccountSelectionMenu(ctx, userId);
});

function buildAccountSelectionKeyboard(userId) {
  const s = getSession(userId);
  const sel = new Set(s.selectedAccountIndices);
  const connected = getAllStatuses().filter((a) => a.status === "connected");
  const rows = connected.map((a) => {
    const hasScript = readScript(a.index + 1).length > 0;
    return [Markup.button.callback(
      `${sel.has(a.index) ? "✅" : "◻️"} Account ${a.index+1} — ${a.phone.slice(-5)}${hasScript ? "" : " ⚠️"}`,
      `tog_acc_${a.index}`,
    )];
  });
  const count = s.selectedAccountIndices.length;
  rows.push([Markup.button.callback(`🚀 Start — ${count} account${count !== 1 ? "s" : ""} selected`, "confirm_broadcast")]);
  rows.push([Markup.button.callback("🔙 Main Menu","back_menu")]);
  return Markup.inlineKeyboard(rows);
}

async function showAccountSelectionMenu(ctx, userId) {
  const s = getSession(userId);
  const text = `🚀 *Broadcast Setup*\n\n${s.conversationMode ? "💬 Conversation mode" : "📢 Normal mode"}\n\nKaunse accounts use karne hain?\n_(⚠️ = script nahi hai)_`;
  const kb = buildAccountSelectionKeyboard(userId);
  if (s.selectionMsgId) {
    try {
      await ctx.telegram.editMessageText(ctx.chat.id, s.selectionMsgId, undefined, text, { parse_mode: "Markdown", reply_markup: kb.reply_markup });
      return;
    } catch {}
  }
  const m = await ctx.reply(text, { parse_mode: "Markdown", ...kb });
  updateSession(userId, { selectionMsgId: m.message_id });
}

bot.action(/^tog_acc_(\d+)$/, async (ctx) => {
  await ctx.answerCbQuery();
  const userId = ctx.from.id;
  const idx = parseInt(ctx.match[1]);
  const sel = new Set(getSession(userId).selectedAccountIndices);
  sel.has(idx) ? sel.delete(idx) : sel.add(idx);
  updateSession(userId, { selectedAccountIndices: [...sel] });
  await showAccountSelectionMenu(ctx, userId);
});

bot.action("confirm_broadcast", async (ctx) => {
  const userId = ctx.from.id;
  const s = getSession(userId);
  const valid = s.selectedAccountIndices.filter((idx) => readScript(idx + 1).length > 0);

  if (!s.selectedAccountIndices.length) {
    await ctx.answerCbQuery("⚠️ Kam se kam 1 account chunein!", { show_alert: true }); return;
  }
  if (!valid.length) {
    await ctx.answerCbQuery("⚠️ Chunein hue accounts ka koi script nahi!", { show_alert: true }); return;
  }

  await ctx.answerCbQuery();
  updateSession(userId, { selectionMsgId: undefined });
  const loadMsg = await ctx.reply("⏳ Groups load ho rahe hain...");

  const accountSelections = [];
  for (const idx of valid) {
    const groups = await getAllGroups(idx);
    accountSelections.push({ accountIndex: idx, groups, groupIds: groups.map((g) => g.id) });
  }

  try { await ctx.telegram.deleteMessage(ctx.chat.id, loadMsg.message_id); } catch {}

  const totalGroups = accountSelections.reduce((sum, a) => sum + a.groupIds.length, 0);
  if (totalGroups === 0) {
    await ctx.reply("❌ Selected accounts mein koi group nahi!\nWhatsApp par kisi group mein join karein.",
      Markup.inlineKeyboard([[Markup.button.callback("🔙 Wapas","back_menu")]]));
    return;
  }

  const endTime = s.scheduleDays !== null ? Date.now() + s.scheduleDays * 86400000 : null;
  await _startBroadcast(ctx, userId, accountSelections, endTime, s.repeatHours, s.delaySeconds, s.conversationMode, false);
});

// ─── Broadcast core ─────────────────────────────────────────────────────
async function _startBroadcast(ctx, userId, accountSelections, endTime, repeatHours, delaySeconds, conversationMode, isResume) {
  const chatId = ctx?.chat?.id ?? userId;
  const flag = startSchedule(userId);

  // Persist to MongoDB
  await ActiveBroadcast.findOneAndUpdate(
    { userId },
    {
      userId, chatId, active: true, broadcastEndTime: endTime,
      ...(isResume ? {} : { broadcastCycles: 0 }),
      repeatHours, delaySeconds, conversationMode,
      accountSelections: accountSelections.map((a) => ({
        accountIndex: a.accountIndex,
        groupIds: a.groupIds,
        groups: a.groups,
      })),
    },
    { upsert: true }
  );

  const totalGroups = accountSelections.reduce((sum, a) => sum + a.groupIds.length, 0);
  const schedText = endTime === null
    ? `♾️ Nonstop — Har *${fmtHours(repeatHours)}* mein repeat`
    : `📅 Duration: *${fmtLeft(endTime)}* — Har *${fmtHours(repeatHours)}* mein repeat`;

  if (isResume) {
    await bot.telegram.sendMessage(chatId,
      `♻️ *Broadcast Resume Ho Gaya!*\nBot restart ke baad continue ho raha hai.\n📱 Accounts: *${accountSelections.length}* | Groups: *${totalGroups}*`,
      { parse_mode: "Markdown", ...mainMenu(userId) },
    ).catch(() => {});
  } else {
    await ctx.reply(
      `🚀 *Broadcast Shuru Ho Gaya!*\n\n${schedText}\n📱 Accounts: *${accountSelections.length}*\n📋 Groups: *${totalGroups}*\n💬 Mode: *${conversationMode ? "Conversation" : "Normal"}*\n\n_🛑 Band karne ke liye button dabao._`,
      { parse_mode: "Markdown", ...mainMenu(userId) },
    );
  }

  _broadcastLoop(userId, chatId, accountSelections, endTime, repeatHours, delaySeconds, conversationMode, flag);
}

function _broadcastLoop(userId, chatId, accountSelections, endTime, repeatHours, delaySeconds, conversationMode, flag) {
  async function loop() {
    while (!flag.stopped) {
      // Check if schedule expired
      if (endTime !== null && Date.now() >= endTime) {
        stopSchedule(userId);
        await ActiveBroadcast.findOneAndUpdate({ userId }, { active: false }).catch(() => {});
        const db = await ActiveBroadcast.findOne({ userId }).catch(() => null);
        await bot.telegram.sendMessage(chatId,
          `✅ *Schedule Complete!*\n🔁 Total cycles: *${db?.broadcastCycles ?? "?"}*`,
          { parse_mode: "Markdown", ...mainMenu(userId) },
        ).catch(() => {});
        break;
      }

      const db = await ActiveBroadcast.findOne({ userId }).catch(() => null);
      const cycleNum = (db?.broadcastCycles ?? 0) + 1;
      const delay = db?.delaySeconds ?? delaySeconds;
      const convMode = db?.conversationMode ?? conversationMode;

      let sent = 0, failed = 0;
      const buildStatus = (extra = "⏳ Chal raha hai...") =>
        `📊 *Cycle #${cycleNum}*\n━━━━━━━━━━━━━━━\n` +
        `📱 Accounts: ${accountSelections.length} | 💬 ${convMode ? "Conversation" : "Normal"}\n` +
        `📤 Sent: *${sent}* | ❌ Failed: *${failed}*\n` +
        `🔁 Done cycles: *${db?.broadcastCycles ?? 0}*\n` +
        `⏳ Time left: *${fmtLeft(endTime)}*\n\n${extra}`;

      let statusMsgId;
      try { const m = await bot.telegram.sendMessage(chatId, buildStatus(), { parse_mode: "Markdown" }); statusMsgId = m.message_id; } catch {}

      const refresh = async (extra) => {
        if (!statusMsgId) return;
        try { await bot.telegram.editMessageText(chatId, statusMsgId, undefined, buildStatus(extra), { parse_mode: "Markdown" }); } catch {}
      };

      if (convMode && accountSelections.length >= 2) {
        // ── CONVERSATION MODE — pair accounts ──
        for (let pi = 0; pi < accountSelections.length; pi += 2) {
          if (flag.stopped) break;
          const a1 = accountSelections[pi];
          const a2 = accountSelections[pi + 1];
          const sc1 = readScript(a1.accountIndex + 1);

          if (!a2) {
            // Odd account at end — send normally
            for (const gId of a1.groupIds) {
              if (flag.stopped) break;
              const gName = a1.groups.find((g) => g.id === gId)?.name ?? gId;
              const ok = await sendMessageToGroup(a1.accountIndex, gId, randomMessage(sc1));
              ok ? sent++ : failed++;
              await refresh(`📤 Acc${a1.accountIndex+1} → _${gName}_`);
              await sleep(delay * 1000);
            }
            continue;
          }

          const sc2 = readScript(a2.accountIndex + 1);
          const a2Set = new Set(a2.groupIds);

          // Shared groups — conversation style (a1 sends, pause, a2 replies)
          for (const gId of a1.groupIds) {
            if (flag.stopped) break;
            const gName = a1.groups.find((g) => g.id === gId)?.name ?? gId;
            const ok1 = await sendMessageToGroup(a1.accountIndex, gId, randomMessage(sc1));
            ok1 ? sent++ : failed++;
            await refresh(`💬 Acc${a1.accountIndex+1} → _${gName}_`);

            if (a2Set.has(gId)) {
              // Wait 3-8 sec to look natural, then reply from a2
              await sleep(Math.max(3000, delay * 500) + Math.floor(Math.random() * 3000));
              if (!flag.stopped) {
                const ok2 = await sendMessageToGroup(a2.accountIndex, gId, randomMessage(sc2));
                ok2 ? sent++ : failed++;
                await refresh(`💬 Acc${a2.accountIndex+1} ↩️ _${gName}_`);
              }
            }
            await sleep(delay * 1000);
          }

          // Groups only in a2 — send normally
          for (const gId of a2.groupIds) {
            if (flag.stopped || new Set(a1.groupIds).has(gId)) continue;
            const gName = a2.groups.find((g) => g.id === gId)?.name ?? gId;
            const ok = await sendMessageToGroup(a2.accountIndex, gId, randomMessage(sc2));
            ok ? sent++ : failed++;
            await refresh(`📤 Acc${a2.accountIndex+1} → _${gName}_`);
            await sleep(delay * 1000);
          }
        }
      } else {
        // ── NORMAL MODE — each account independently ──
        for (const acc of accountSelections) {
          if (flag.stopped) break;
          const sc = readScript(acc.accountIndex + 1);
          for (const gId of acc.groupIds) {
            if (flag.stopped) break;
            const gName = acc.groups.find((g) => g.id === gId)?.name ?? gId;
            const ok = await sendMessageToGroup(acc.accountIndex, gId, randomMessage(sc));
            ok ? sent++ : failed++;
            await refresh(`📤 Acc${acc.accountIndex+1} → _${gName}_`);
            await sleep(delay * 1000);
          }
        }
      }

      if (flag.stopped) break;

      await ActiveBroadcast.findOneAndUpdate({ userId }, { $inc: { broadcastCycles: 1 } }).catch(() => {});
      await refresh(`✅ Cycle #${cycleNum} complete! Sent: ${sent} | Failed: ${failed}`);

      const waitMs = repeatHours * 3600000;
      await bot.telegram.sendMessage(chatId,
        `✅ *Cycle #${cycleNum} Complete!*\n📤 Sent: ${sent} | ❌ Failed: ${failed}\n\n⏰ Agla: *${new Date(Date.now() + waitMs).toLocaleTimeString("en-IN")}* par`,
        { parse_mode: "Markdown" },
      ).catch(() => {});

      const waitUntil = Date.now() + waitMs;
      while (!flag.stopped && Date.now() < waitUntil) await sleep(30000);
    }
  }
  loop().catch((e) => console.error("[BroadcastLoop]", e));
}

// ─── Back ──────────────────────────────────────────────────────────────
bot.action("back_menu", async (ctx) => {
  await ctx.answerCbQuery();
  updateSession(ctx.from.id, { selectionMsgId: undefined, awaitingPhoneForIndex: null });
  await ctx.reply("🏠 *Main Menu:*", { parse_mode: "Markdown", ...mainMenu(ctx.from.id) });
});

// ─── Text handler — phone number input ────────────────────────────────
bot.on("text", async (ctx) => {
  const userId = ctx.from.id;
  const s = getSession(userId);
  const text = ctx.message.text.trim();
  if (text.startsWith("/")) return;

  const idx = s.awaitingPhoneForIndex;
  if (idx !== null && idx !== undefined) {
    const phone = text.replace(/[^0-9]/g, "");
    if (phone.length < 10) {
      await ctx.reply("❌ Invalid number. Example: `919876543210`",
        { parse_mode: "Markdown", ...Markup.inlineKeyboard([[Markup.button.callback("🔙 Accounts","menu_accounts")]]) });
      return;
    }
    updateSession(userId, { awaitingPhoneForIndex: null });
    const waitMsg = await ctx.reply(
      `⏳ *WA Account ${idx+1}* ke liye pairing code generate ho raha hai...\n_15-30 sec mein code aayega_`,
      { parse_mode: "Markdown" },
    );

    pendingPairingCbs.set(idx, async (code) => {
      try { await ctx.telegram.deleteMessage(ctx.chat.id, waitMsg.message_id); } catch {}
      if (!code) {
        await ctx.reply("❌ *Code generate nahi hua.* Dobara try karein.",
          { parse_mode: "Markdown", ...Markup.inlineKeyboard([
            [Markup.button.callback("🔄 Try Again", `acc_${idx}`)],
            [Markup.button.callback("🔙 Accounts","menu_accounts")],
          ])});
        return;
      }
      await ctx.reply(
        `🔑 *Pairing Code — Account ${idx+1}*\n\n\`${code}\`\n\n` +
        `*Steps:*\n1. WhatsApp open karein\n2. *Settings → Linked Devices → Link a Device*\n3. *Link with phone number* tap karein\n4. Upar ka code enter karein\n\n` +
        `⚠️ *Code sirf 60 seconds valid hai — jaldi enter karein!*\n⏳ Connect hone ka wait ho raha hai...`,
        { parse_mode: "Markdown", ...Markup.inlineKeyboard([
          [Markup.button.callback("🔄 Naya Code Mangwao", `reset_${idx}`)],
          [Markup.button.callback("🔙 Menu","back_menu")],
        ])},
      );
    });

    pendingReadyCbs.set(idx, async () => {
      await ctx.reply(`✅ *WA Account ${idx+1} Connected!*\n📱 \`${phone}\``,
        { parse_mode: "Markdown", ...mainMenu(userId) });
    });

    connectAccount(idx, phone).catch(async (err) => {
      pendingPairingCbs.delete(idx);
      pendingReadyCbs.delete(idx);
      await ctx.reply(`❌ Error: \`${err.message}\``,
        { parse_mode: "Markdown", ...Markup.inlineKeyboard([[Markup.button.callback("🔙 Accounts","menu_accounts")]]) });
    });
    return;
  }

  await sendMainMenu(ctx, "👇 Menu se option chunein:");
});

bot.catch((err) => { console.error("[Bot Error]", err.message); });

// ─── Express health server ──────────────────────────────────────────────
const app = express();
const PORT = process.env.PORT || 3000;

app.get("/", (_req, res) => res.send(`
  <html><body style="font-family:sans-serif;text-align:center;padding:50px;background:#0a0a0a;color:#fff">
    <h2>✅ WhatsApp Broadcast Bot v5</h2>
    <p style="color:#4ade80">Chal raha hai 🟢</p>
    <p>Uptime: ${Math.floor(process.uptime())}s | WA Connected: ${getConnectedCount()}/${MAX_ACCOUNTS}</p>
  </body></html>`));

app.get("/health", (_req, res) => res.json({
  status: "ok",
  uptime: `${Math.floor(process.uptime())}s`,
  accounts: getAllStatuses().map((a) => ({ n: a.index + 1, status: a.status, phone: a.phone || null })),
  ts: new Date().toISOString(),
}));

app.listen(PORT, () => console.log(`🌐 HTTP server — port ${PORT}`));

// ─── Self-ping (keeps Render free tier alive) ──────────────────────────
function selfPing() {
  const url = process.env.RENDER_EXTERNAL_URL || process.env.SELF_URL;
  if (!url) return;
  const fullUrl = url.startsWith("http") ? url : `https://${url}`;
  const client = fullUrl.startsWith("https") ? https : http;
  client.get(`${fullUrl}/health`, (r) => {
    console.log(`[Ping] ${r.statusCode}`);
  }).on("error", (e) => console.error("[Ping Error]", e.message));
}
setTimeout(() => { selfPing(); setInterval(selfPing, 120000); }, 60000);

// ─── Resume broadcasts after restart ────────────────────────────────────
async function resumeBroadcasts() {
  const broadcasts = await ActiveBroadcast.find({ active: true }).catch(() => []);
  if (!broadcasts.length) { console.log("[Startup] No broadcasts to resume."); return; }
  console.log(`[Startup] ${broadcasts.length} broadcast(s) to resume — waiting 40s for WA reconnect...`);
  await sleep(40000);

  for (const b of broadcasts) {
    if (!b.accountSelections?.length) continue;
    const anyConnected = b.accountSelections.some((a) => getStatus(a.accountIndex) === "connected");
    if (!anyConnected) {
      console.log(`[Startup] User ${b.userId} — no accounts connected, broadcast stopped.`);
      await ActiveBroadcast.findOneAndUpdate({ userId: b.userId }, { active: false }).catch(() => {});
      continue;
    }
    const endTime = b.broadcastEndTime && b.broadcastEndTime > Date.now() ? b.broadcastEndTime : null;
    // Restore session settings
    updateSession(b.userId, {
      repeatHours: b.repeatHours,
      delaySeconds: b.delaySeconds,
      conversationMode: b.conversationMode,
    });
    const fakeCtx = { chat: { id: b.chatId } };
    await _startBroadcast(
      fakeCtx, b.userId,
      b.accountSelections.map((a) => ({ accountIndex: a.accountIndex, groups: a.groups, groupIds: a.groupIds })),
      endTime, b.repeatHours, b.delaySeconds, b.conversationMode,
      true, // isResume
    );
    console.log(`[Startup] Broadcast resumed for user ${b.userId}`);
  }
}

// ─── Main startup ────────────────────────────────────────────────────────
async function main() {
  await connectDB();
  reconnectSavedAccounts().catch((e) => console.error("[Reconnect Error]", e.message));
  await bot.launch({ dropPendingUpdates: true });
  console.log(`✅ Bot v5 running! Owner: ${OWNER_ID || "NOT SET"} | Max accounts: ${MAX_ACCOUNTS}`);
  resumeBroadcasts().catch((e) => console.error("[Resume Error]", e.message));
}

main().catch((err) => { console.error("❌ Fatal:", err.message); process.exit(1); });
process.once("SIGINT", () => bot.stop("SIGINT"));
process.once("SIGTERM", () => bot.stop("SIGTERM"));
