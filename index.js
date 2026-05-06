const { Telegraf, Markup } = require("telegraf");
const { getSession, updateSession } = require("./src/session");
const { readScript, randomMessage } = require("./src/scripts");
const { startSchedule, stopSchedule, isActive } = require("./src/scheduler");
const {
  setCallbacks, getStatus, getPhone,
  connectAccount, disconnectAccount,
  getAllGroups, sendMessageToGroup,
} = require("./src/whatsapp-manager");
const http = require("http");
const https = require("https");

const TOKEN = process.env.TELEGRAM_BOT_TOKEN;
if (!TOKEN) throw new Error("❌ TELEGRAM_BOT_TOKEN environment variable not set!");

const bot = new Telegraf(TOKEN);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const MAX_GROUPS = 48;

// ─── Helpers ───────────────────────────────────────────────────────────
function statusEmoji(s) {
  if (s === "connected") return "✅";
  if (s === "connecting") return "⏳";
  return "❌";
}

function formatDuration(days) {
  if (days === null) return "Nonstop ♾️";
  if (days === 1) return "1 Din";
  return `${days} Din`;
}

function formatRepeat(hours) {
  if (hours < 1) return `${hours * 60} min`;
  if (hours === 1) return "1 Ghanta";
  if (hours < 24) return `${hours} Ghante`;
  return `${hours / 24} Din`;
}

function formatTimeLeft(endTime) {
  if (endTime === null) return "Nonstop ♾️";
  const ms = endTime - Date.now();
  if (ms <= 0) return "Khatam";
  const h = Math.floor(ms / 3600000);
  const m = Math.floor((ms % 3600000) / 60000);
  if (h >= 24) return `${Math.floor(h / 24)}d ${h % 24}h baaki`;
  return `${h}h ${m}m baaki`;
}

function mainMenu(userId) {
  const s1 = getStatus(0), s2 = getStatus(1);
  const p1 = getPhone(0) || "Connect nahi";
  const p2 = getPhone(1) || "Connect nahi";
  const active = userId ? isActive(userId) : false;
  const rows = [
    [Markup.button.callback(`${statusEmoji(s1)} WA Account 1 — ${p1}`, "menu_wa1")],
    [Markup.button.callback(`${statusEmoji(s2)} WA Account 2 — ${p2}`, "menu_wa2")],
    [
      Markup.button.callback("⏱️ Message Delay", "menu_delay"),
      Markup.button.callback("⏰ Schedule", "menu_schedule"),
    ],
  ];
  if (active) {
    rows.push([Markup.button.callback("🛑 Broadcast BAND Karein", "stop_broadcast")]);
  } else {
    rows.push([Markup.button.callback("🚀 Broadcast Shuru Karein", "menu_broadcast")]);
  }
  rows.push([Markup.button.callback("📊 Status Dekhein", "menu_status")]);
  return Markup.inlineKeyboard(rows);
}

async function sendMainMenu(ctx, text) {
  await ctx.reply(
    text || "👋 *WhatsApp Broadcast Bot*\n\nMenu se option chunein:",
    { parse_mode: "Markdown", ...mainMenu(ctx.from?.id) },
  );
}

// ─── WhatsApp callbacks ────────────────────────────────────────────────
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
  onDisconnected: (_i) => {},
});

// ─── Group selection ───────────────────────────────────────────────────
function groupSelectionKeyboard(waIndex, groups, selectedIds) {
  const selSet = new Set(selectedIds);
  const shown = groups.slice(0, MAX_GROUPS);
  const allSelected = shown.every((g) => selSet.has(g.id));
  const rows = [];
  rows.push([Markup.button.callback(
    allSelected ? "◻️ Sab Deselect Karein" : "✅ Sab Select Karein",
    allSelected ? `da${waIndex}` : `sa${waIndex}`,
  )]);
  shown.forEach((g, i) => {
    rows.push([Markup.button.callback(`${selSet.has(g.id) ? "✅" : "◻️"} ${g.name.slice(0, 28)}`, `tg${waIndex}_${i}`)]);
  });
  const count = selectedIds.length;
  rows.push([Markup.button.callback(`🚀 Confirm — ${count} group${count !== 1 ? "s" : ""} selected`, `confirm_wa${waIndex}`)]);
  rows.push([Markup.button.callback("🔙 Main Menu", "back_menu")]);
  return Markup.inlineKeyboard(rows);
}

async function showGroupSelection(ctx, waIndex, userId) {
  const session = getSession(userId);
  const groups = waIndex === 1 ? session.wa1Groups : session.wa2Groups;
  const selectedIds = waIndex === 1 ? session.selectedWa1Ids : session.selectedWa2Ids;
  const phone = getPhone(waIndex - 1) || "—";
  const text =
    `📱 *WA Account ${waIndex} (${phone})*\n` +
    `Groups: *${groups.length}* | Selected: *${selectedIds.length}*\n\n` +
    `Jinhe message bhejna hai unhe ✅ select karein:`;
  const kb = groupSelectionKeyboard(waIndex, groups, selectedIds);
  if (session.selectionMsgId) {
    try {
      await ctx.telegram.editMessageText(ctx.chat.id, session.selectionMsgId, undefined, text, {
        parse_mode: "Markdown", reply_markup: kb.reply_markup,
      });
      return;
    } catch {}
  }
  const sent = await ctx.reply(text, { parse_mode: "Markdown", ...kb });
  updateSession(userId, { selectionMsgId: sent.message_id });
}

// ─── Commands ──────────────────────────────────────────────────────────
bot.start(async (ctx) => { await sendMainMenu(ctx); });
bot.command("menu", async (ctx) => { await sendMainMenu(ctx); });

// ─── WA connect/logout ─────────────────────────────────────────────────
async function handleConnectMenu(ctx, index) {
  const userId = ctx.from.id;
  const status = getStatus(index), phone = getPhone(index), accNum = index + 1;
  if (status === "connected") {
    await ctx.reply(`📱 *WhatsApp Account ${accNum}*\n✅ Connected: \`${phone}\``, {
      parse_mode: "Markdown",
      ...Markup.inlineKeyboard([
        [Markup.button.callback(`🔌 Account ${accNum} Logout Karein`, `logout_${index}`)],
        [Markup.button.callback("🔙 Main Menu", "back_menu")],
      ]),
    });
  } else if (status === "connecting") {
    await ctx.reply("⏳ *Abhi connect ho raha hai...* Wait karein.", {
      parse_mode: "Markdown",
      ...Markup.inlineKeyboard([[Markup.button.callback("🔙 Main Menu", "back_menu")]]),
    });
  } else {
    updateSession(userId, { state: index === 0 ? "awaiting_phone1" : "awaiting_phone2" });
    await ctx.reply(
      `📱 *WhatsApp Account ${accNum} Connect Karein*\n\nPhone number bhejein (country code ke saath):\nExample: \`919876543210\``,
      { parse_mode: "Markdown", ...Markup.inlineKeyboard([[Markup.button.callback("🔙 Main Menu", "back_menu")]]) },
    );
  }
}

bot.action("menu_wa1", async (ctx) => { await ctx.answerCbQuery(); await handleConnectMenu(ctx, 0); });
bot.action("menu_wa2", async (ctx) => { await ctx.answerCbQuery(); await handleConnectMenu(ctx, 1); });

bot.action(/^logout_(\d)$/, async (ctx) => {
  await ctx.answerCbQuery("Logout ho raha hai...");
  const index = parseInt(ctx.match[1]);
  await ctx.editMessageText(`⏳ WhatsApp Account ${index + 1} logout ho raha hai...`);
  await disconnectAccount(index);
  await ctx.editMessageText(`✅ *WhatsApp Account ${index + 1} logout ho gaya!*`, { parse_mode: "Markdown" });
  await sleep(700);
  await sendMainMenu(ctx);
});

// ─── Message Delay ─────────────────────────────────────────────────────
bot.action("menu_delay", async (ctx) => {
  await ctx.answerCbQuery();
  const session = getSession(ctx.from.id);
  await ctx.reply(
    `⏱️ *Message Delay Set Karein*\nCurrent: *${session.delaySeconds} seconds*\n\nHar group ko message bhejne ke baad kitna wait karein?`,
    {
      parse_mode: "Markdown",
      ...Markup.inlineKeyboard([
        [Markup.button.callback("1s", "delay_1"), Markup.button.callback("3s", "delay_3"), Markup.button.callback("5s", "delay_5"), Markup.button.callback("10s", "delay_10"), Markup.button.callback("30s", "delay_30")],
        [Markup.button.callback("🔙 Main Menu", "back_menu")],
      ]),
    },
  );
});

[1, 3, 5, 10, 30].forEach((d) => {
  bot.action(`delay_${d}`, async (ctx) => {
    await ctx.answerCbQuery();
    updateSession(ctx.from.id, { delaySeconds: d });
    await ctx.editMessageText(`✅ Message delay set: *${d} seconds*`, { parse_mode: "Markdown" });
    await sleep(500);
    await sendMainMenu(ctx);
  });
});

// ─── Schedule ──────────────────────────────────────────────────────────
bot.action("menu_schedule", async (ctx) => {
  await ctx.answerCbQuery();
  const session = getSession(ctx.from.id);
  await ctx.reply(
    `⏰ *Schedule Set Karein*\n\n*Current settings:*\n• Duration: *${formatDuration(session.scheduleDays)}*\n• Repeat: *Har ${formatRepeat(session.repeatHours)}*\n\nPehle *kitne din chalana hai* chunein:`,
    {
      parse_mode: "Markdown",
      ...Markup.inlineKeyboard([
        [Markup.button.callback("♾️ Nonstop", "sch_days_0"), Markup.button.callback("1 Din", "sch_days_1"), Markup.button.callback("3 Din", "sch_days_3")],
        [Markup.button.callback("7 Din", "sch_days_7"), Markup.button.callback("10 Din", "sch_days_10"), Markup.button.callback("30 Din", "sch_days_30")],
        [Markup.button.callback("🔙 Main Menu", "back_menu")],
      ]),
    },
  );
});

[0, 1, 3, 7, 10, 30].forEach((d) => {
  bot.action(`sch_days_${d}`, async (ctx) => {
    await ctx.answerCbQuery();
    const days = d === 0 ? null : d;
    updateSession(ctx.from.id, { scheduleDays: days });
    await ctx.editMessageText(
      `✅ Duration set: *${formatDuration(days)}*\n\nAb *kitni baar repeat* karna hai chunein:\n_(Ek cycle complete hone ke baad kitna wait karein?)_`,
      {
        parse_mode: "Markdown",
        ...Markup.inlineKeyboard([
          [Markup.button.callback("30 min", "sch_rep_0.5"), Markup.button.callback("1 Ghanta", "sch_rep_1"), Markup.button.callback("2 Ghante", "sch_rep_2")],
          [Markup.button.callback("6 Ghante", "sch_rep_6"), Markup.button.callback("12 Ghante", "sch_rep_12"), Markup.button.callback("24 Ghante", "sch_rep_24")],
          [Markup.button.callback("🔙 Main Menu", "back_menu")],
        ]),
      },
    );
  });
});

[0.5, 1, 2, 6, 12, 24].forEach((h) => {
  bot.action(`sch_rep_${h}`, async (ctx) => {
    await ctx.answerCbQuery();
    const session = getSession(ctx.from.id);
    updateSession(ctx.from.id, { repeatHours: h });
    await ctx.editMessageText(
      `✅ *Schedule Save Ho Gaya!*\n\n⏰ Duration: *${formatDuration(session.scheduleDays)}*\n🔄 Repeat: *Har ${formatRepeat(h)}*\n\n_Ab "Broadcast Shuru Karein" dabao._`,
      { parse_mode: "Markdown" },
    );
    await sleep(600);
    await sendMainMenu(ctx);
  });
});

// ─── Status ─────────────────────────────────────────────────────────────
bot.action("menu_status", async (ctx) => {
  await ctx.answerCbQuery();
  const userId = ctx.from.id;
  const session = getSession(userId);
  const sc1 = readScript(1), sc2 = readScript(2);
  await ctx.reply(
    `📊 *Bot Status*\n\n` +
    `*📱 WA Account 1:* ${statusEmoji(getStatus(0))} ${getStatus(0).toUpperCase()}\n` +
    (getPhone(0) ? `  Number: \`${getPhone(0)}\`\n` : "") +
    `\n*📱 WA Account 2:* ${statusEmoji(getStatus(1))} ${getStatus(1).toUpperCase()}\n` +
    (getPhone(1) ? `  Number: \`${getPhone(1)}\`\n` : "") +
    `\n*Script 1:* ${sc1.length} messages\n` +
    `*Script 2:* ${sc2.length} messages\n\n` +
    `*⏱️ Message Delay:* ${session.delaySeconds} sec\n` +
    `*⏰ Duration:* ${formatDuration(session.scheduleDays)}\n` +
    `*🔄 Repeat:* Har ${formatRepeat(session.repeatHours)}\n` +
    `*🔁 Cycles:* ${session.broadcastCycles}\n` +
    `*📡 Status:* ${isActive(userId) ? "🟢 Chal raha hai" : "🔴 Band hai"}\n` +
    (session.broadcastEndTime ? `*⏳ Time Left:* ${formatTimeLeft(session.broadcastEndTime)}\n` : ""),
    {
      parse_mode: "Markdown",
      ...Markup.inlineKeyboard([[Markup.button.callback("🔙 Main Menu", "back_menu")]]),
    },
  );
});

// ─── Stop broadcast ────────────────────────────────────────────────────
bot.action("stop_broadcast", async (ctx) => {
  await ctx.answerCbQuery("Broadcast band ho raha hai...");
  const userId = ctx.from.id;
  stopSchedule(userId);
  updateSession(userId, { broadcastActive: false, broadcastEndTime: null });
  await ctx.reply("🛑 *Broadcast Band Ho Gaya!*", { parse_mode: "Markdown", ...mainMenu(userId) });
});

// ─── Broadcast start ────────────────────────────────────────────────────
bot.action("menu_broadcast", async (ctx) => {
  await ctx.answerCbQuery();
  const userId = ctx.from.id;
  const s1 = getStatus(0), s2 = getStatus(1);
  const sc1 = readScript(1), sc2 = readScript(2);

  if (s1 !== "connected" && s2 !== "connected") {
    await ctx.reply("❌ Koi bhi WhatsApp account connected nahi!", Markup.inlineKeyboard([
      [Markup.button.callback("📱 WA 1 Connect", "menu_wa1"), Markup.button.callback("📱 WA 2 Connect", "menu_wa2")],
      [Markup.button.callback("🔙 Wapas", "back_menu")],
    ]));
    return;
  }
  if (sc1.length === 0 && sc2.length === 0) {
    await ctx.reply("❌ Dono scripts khali hain!\n\n`data/script1.txt` ya `data/script2.txt` mein messages add karein.", Markup.inlineKeyboard([[Markup.button.callback("🔙 Wapas", "back_menu")]]));
    return;
  }

  await ctx.reply("⏳ Groups load ho rahe hain...");
  updateSession(userId, { selectionMsgId: undefined, broadcastCycles: 0 });

  if (s1 === "connected" && sc1.length > 0) {
    const groups = await getAllGroups(0);
    updateSession(userId, { state: "selecting_wa1", wa1Groups: groups, selectedWa1Ids: groups.map((g) => g.id) });
    await showGroupSelection(ctx, 1, userId);
  } else {
    const groups = await getAllGroups(1);
    updateSession(userId, { state: "selecting_wa2", wa2Groups: groups, selectedWa2Ids: groups.map((g) => g.id) });
    await showGroupSelection(ctx, 2, userId);
  }
});

// ─── Group toggles WA1 ──────────────────────────────────────────────────
bot.action(/^tg1_(\d+)$/, async (ctx) => {
  await ctx.answerCbQuery();
  const userId = ctx.from.id;
  const session = getSession(userId);
  const group = session.wa1Groups[parseInt(ctx.match[1])];
  if (!group) return;
  const sel = new Set(session.selectedWa1Ids);
  sel.has(group.id) ? sel.delete(group.id) : sel.add(group.id);
  updateSession(userId, { selectedWa1Ids: [...sel] });
  await showGroupSelection(ctx, 1, userId);
});
bot.action("sa1", async (ctx) => {
  await ctx.answerCbQuery();
  const s = getSession(ctx.from.id);
  updateSession(ctx.from.id, { selectedWa1Ids: s.wa1Groups.slice(0, MAX_GROUPS).map((g) => g.id) });
  await showGroupSelection(ctx, 1, ctx.from.id);
});
bot.action("da1", async (ctx) => {
  await ctx.answerCbQuery();
  updateSession(ctx.from.id, { selectedWa1Ids: [] });
  await showGroupSelection(ctx, 1, ctx.from.id);
});

// ─── Group toggles WA2 ──────────────────────────────────────────────────
bot.action(/^tg2_(\d+)$/, async (ctx) => {
  await ctx.answerCbQuery();
  const userId = ctx.from.id;
  const session = getSession(userId);
  const group = session.wa2Groups[parseInt(ctx.match[1])];
  if (!group) return;
  const sel = new Set(session.selectedWa2Ids);
  sel.has(group.id) ? sel.delete(group.id) : sel.add(group.id);
  updateSession(userId, { selectedWa2Ids: [...sel] });
  await showGroupSelection(ctx, 2, userId);
});
bot.action("sa2", async (ctx) => {
  await ctx.answerCbQuery();
  const s = getSession(ctx.from.id);
  updateSession(ctx.from.id, { selectedWa2Ids: s.wa2Groups.slice(0, MAX_GROUPS).map((g) => g.id) });
  await showGroupSelection(ctx, 2, ctx.from.id);
});
bot.action("da2", async (ctx) => {
  await ctx.answerCbQuery();
  updateSession(ctx.from.id, { selectedWa2Ids: [] });
  await showGroupSelection(ctx, 2, ctx.from.id);
});

// ─── Confirm WA1 → WA2 or start ────────────────────────────────────────
bot.action("confirm_wa1", async (ctx) => {
  const userId = ctx.from.id;
  const session = getSession(userId);
  if (session.selectedWa1Ids.length === 0) {
    await ctx.answerCbQuery("⚠️ Kam se kam 1 group select karein!", { show_alert: true });
    return;
  }
  await ctx.answerCbQuery();
  const s2 = getStatus(1);
  const sc2 = readScript(2);
  if (s2 === "connected" && sc2.length > 0) {
    const groups = await getAllGroups(1);
    updateSession(userId, { state: "selecting_wa2", wa2Groups: groups, selectedWa2Ids: groups.map((g) => g.id), selectionMsgId: undefined });
    await ctx.reply("✅ WA1 groups confirmed!\n\nAb WA Account 2 ke groups chunein:");
    await showGroupSelection(ctx, 2, userId);
  } else {
    await launchBroadcastLoop(ctx, userId);
  }
});

// ─── Confirm WA2 → start ───────────────────────────────────────────────
bot.action("confirm_wa2", async (ctx) => {
  const userId = ctx.from.id;
  const session = getSession(userId);
  if (session.selectedWa2Ids.length === 0) {
    await ctx.answerCbQuery("⚠️ Kam se kam 1 group select karein!", { show_alert: true });
    return;
  }
  await ctx.answerCbQuery();
  await launchBroadcastLoop(ctx, userId);
});

// ─── Broadcast loop ─────────────────────────────────────────────────────
async function launchBroadcastLoop(ctx, userId) {
  const session = getSession(userId);
  const { scheduleDays, repeatHours, selectedWa1Ids, selectedWa2Ids } = session;

  const endTime = scheduleDays !== null ? Date.now() + scheduleDays * 24 * 60 * 60 * 1000 : null;
  updateSession(userId, { broadcastActive: true, broadcastEndTime: endTime, broadcastCycles: 0, state: "idle" });

  const flag = startSchedule(userId);
  const chatId = ctx.chat.id;

  const scheduleText = scheduleDays === null
    ? `♾️ Nonstop — Har *${formatRepeat(repeatHours)}* mein repeat hoga`
    : `📅 *${scheduleDays} din* tak — Har *${formatRepeat(repeatHours)}* mein repeat\n⏳ Khatam: ${new Date(endTime).toLocaleString("en-IN")}`;

  await ctx.reply(
    `🚀 *Broadcast Schedule Shuru Ho Gaya!*\n\n${scheduleText}\n\n_🛑 Band karne ke liye "Broadcast BAND Karein" dabao._`,
    { parse_mode: "Markdown", ...mainMenu(userId) },
  );

  const runLoop = async () => {
    while (!flag.stopped) {
      if (endTime !== null && Date.now() >= endTime) {
        stopSchedule(userId);
        updateSession(userId, { broadcastActive: false, broadcastEndTime: null });
        try {
          await bot.telegram.sendMessage(chatId,
            `✅ *Schedule Complete!*\n\n📅 ${scheduleDays} din ki chatting khatam ho gayi.\n🔁 Total cycles: *${getSession(userId).broadcastCycles}*`,
            { parse_mode: "Markdown", ...mainMenu(userId) },
          );
        } catch {}
        break;
      }

      const cycleNum = getSession(userId).broadcastCycles + 1;
      const sc1 = readScript(1), sc2 = readScript(2);
      const total = selectedWa1Ids.length + selectedWa2Ids.length;
      let sent = 0, failed = 0;

      const buildStatus = (extra = "⏳ Chal raha hai...") => {
        const s = getSession(userId);
        return (
          `📊 *Cycle #${cycleNum} — Live Status*\n` +
          `━━━━━━━━━━━━━━━━━━\n` +
          `📱 WA1: \`${getPhone(0) || "—"}\`\n` +
          `📱 WA2: \`${getPhone(1) || "—"}\`\n\n` +
          `📍 *Groups:* ${total} (WA1: ${selectedWa1Ids.length} | WA2: ${selectedWa2Ids.length})\n` +
          `📤 *Sent:* ${sent} / ${total}\n` +
          `❌ *Failed:* ${failed}\n` +
          `🔁 *Total Cycles:* ${s.broadcastCycles}\n` +
          `⏳ *Time Left:* ${formatTimeLeft(endTime)}\n\n` +
          extra
        );
      };

      let statusMsgId;
      try {
        const m = await bot.telegram.sendMessage(chatId, buildStatus(), { parse_mode: "Markdown" });
        statusMsgId = m.message_id;
      } catch {}

      const refreshStatus = async (extra) => {
        if (!statusMsgId) return;
        try {
          await bot.telegram.editMessageText(chatId, statusMsgId, undefined, buildStatus(extra), { parse_mode: "Markdown" });
        } catch {}
      };

      // WA1 broadcast
      if (!flag.stopped && getStatus(0) === "connected" && sc1.length > 0) {
        for (const gId of selectedWa1Ids) {
          if (flag.stopped) break;
          const group = getSession(userId).wa1Groups.find((g) => g.id === gId);
          const ok = await sendMessageToGroup(0, gId, randomMessage(sc1));
          if (ok) sent++; else failed++;
          await refreshStatus(`⏳ WA1 → _${group?.name ?? gId}_`);
          await sleep(getSession(userId).delaySeconds * 1000);
        }
      }

      // WA2 broadcast
      if (!flag.stopped && getStatus(1) === "connected" && sc2.length > 0) {
        for (const gId of selectedWa2Ids) {
          if (flag.stopped) break;
          const group = getSession(userId).wa2Groups.find((g) => g.id === gId);
          const ok = await sendMessageToGroup(1, gId, randomMessage(sc2));
          if (ok) sent++; else failed++;
          await refreshStatus(`⏳ WA2 → _${group?.name ?? gId}_`);
          await sleep(getSession(userId).delaySeconds * 1000);
        }
      }

      if (flag.stopped) break;

      const newCycles = getSession(userId).broadcastCycles + 1;
      updateSession(userId, { broadcastCycles: newCycles });
      await refreshStatus(`✅ Cycle #${cycleNum} complete!`);

      const waitMs = repeatHours * 60 * 60 * 1000;
      const nextTime = new Date(Date.now() + waitMs).toLocaleTimeString("en-IN");
      try {
        await bot.telegram.sendMessage(chatId,
          `✅ *Cycle #${cycleNum} Complete!*\n📤 Sent: ${sent} | ❌ Failed: ${failed}\n\n⏰ Agla cycle: *${nextTime}* par`,
          { parse_mode: "Markdown" },
        );
      } catch {}

      const waitUntil = Date.now() + waitMs;
      while (!flag.stopped && Date.now() < waitUntil) {
        await sleep(30000);
      }
    }
  };

  runLoop().catch((err) => console.error("[BroadcastLoop Error]", err));
}

// ─── Back ───────────────────────────────────────────────────────────────
bot.action("back_menu", async (ctx) => {
  await ctx.answerCbQuery();
  updateSession(ctx.from.id, { state: "idle", selectionMsgId: undefined });
  await ctx.reply("🏠 Main Menu:", mainMenu(ctx.from.id));
});

// ─── Text handler ───────────────────────────────────────────────────────
bot.on("text", async (ctx) => {
  const userId = ctx.from.id;
  const session = getSession(userId);
  const text = ctx.message.text.trim();
  if (text.startsWith("/")) return;

  if (session.state === "awaiting_phone1" || session.state === "awaiting_phone2") {
    const index = session.state === "awaiting_phone1" ? 0 : 1;
    const phone = text.replace(/[^0-9]/g, "");
    if (phone.length < 10) {
      await ctx.reply("❌ Invalid number.\nExample: `919876543210`", {
        parse_mode: "Markdown",
        ...Markup.inlineKeyboard([[Markup.button.callback("🔙 Wapas", "back_menu")]]),
      });
      return;
    }
    updateSession(userId, { state: "idle" });
    await ctx.reply(`⏳ *WA Account ${index + 1}* ke liye pairing code generate ho raha hai...\n_(30-60 seconds lag sakte hain)_`, { parse_mode: "Markdown" });

    pendingPairingCbs.set(index, async (code) => {
      const fmt = code.match(/.{1,4}/g)?.join("-") || code;
      await ctx.reply(
        `🔑 *Pairing Code — Account ${index + 1}*\n\n\`${fmt}\`\n\n*Steps:*\n1. WhatsApp → *Settings → Linked Devices*\n2. *Link a Device → Link with phone number*\n3. Code enter karein\n\n⏳ Connect hone ka wait ho raha hai...`,
        { parse_mode: "Markdown", ...Markup.inlineKeyboard([[Markup.button.callback("🔙 Main Menu", "back_menu")]]) },
      );
    });
    pendingReadyCbs.set(index, async () => {
      await ctx.reply(`✅ *WA Account ${index + 1} Connected!*\n📱 \`${phone}\``, { parse_mode: "Markdown", ...mainMenu(userId) });
    });

    try {
      await connectAccount(index, phone);
    } catch (err) {
      console.error("Connect error:", err.message);
      pendingPairingCbs.delete(index);
      pendingReadyCbs.delete(index);
      await ctx.reply("❌ Error aaya. Dobara try karein.", Markup.inlineKeyboard([[Markup.button.callback("🔙 Wapas", "back_menu")]]));
    }
    return;
  }

  await sendMainMenu(ctx, "👇 Menu se option chunein:");
});

bot.catch((err) => console.error("[Bot Error]", err));

// ─── Express HTTP Server (Render ke liye zaroori) ──────────────────────
const express = require("express");
const app = express();
const PORT = process.env.PORT || 3000;

app.get("/", (_req, res) => {
  res.send(`
    <html><body style="font-family:sans-serif;text-align:center;padding:50px">
      <h2>✅ WhatsApp Broadcast Bot</h2>
      <p>Bot chal raha hai! 🟢</p>
      <p>Telegram pe /start karein</p>
    </body></html>
  `);
});

app.get("/health", (_req, res) => {
  res.json({
    status: "ok",
    uptime: Math.floor(process.uptime()) + "s",
    wa1: getStatus(0),
    wa2: getStatus(1),
    timestamp: new Date().toISOString(),
  });
});

app.listen(PORT, () => {
  console.log(`🌐 Web server chal raha hai — port ${PORT}`);
});

// ─── Self-ping (Render free tier sleep prevent karne ke liye) ──────────
function selfPing() {
  const selfUrl = process.env.RENDER_EXTERNAL_URL || process.env.SELF_URL;
  if (!selfUrl) {
    console.log("[Ping] RENDER_EXTERNAL_URL set nahi — ping skip");
    return;
  }
  const url = selfUrl.startsWith("https") ? selfUrl : `https://${selfUrl}`;
  const client = url.startsWith("https") ? https : http;
  client.get(`${url}/health`, (res) => {
    console.log(`[Ping] ✅ Self-ping OK — ${res.statusCode} — ${new Date().toLocaleTimeString()}`);
  }).on("error", (err) => {
    console.error("[Ping] ❌ Error:", err.message);
  });
}

// Pehla ping 1 minute baad, phir har 2 minute
setTimeout(() => {
  selfPing();
  setInterval(selfPing, 2 * 60 * 1000);
}, 60 * 1000);

// ─── Bot launch ────────────────────────────────────────────────────────
bot.launch({ dropPendingUpdates: true }).then(() => {
  console.log("✅ WhatsApp Broadcast Bot chal raha hai!");
  console.log("📝 Script files: data/script1.txt & data/script2.txt");
});

process.once("SIGINT", () => bot.stop("SIGINT"));
process.once("SIGTERM", () => bot.stop("SIGTERM"));
