/**
 * WhatsApp Group Manager Bot v6
 * - 10 WhatsApp accounts support
 * - MongoDB persistence
 * - Group Manager: member list, pending requests, promote/demote, AI auto-accept
 * - Owner-only access
 * - Render.com ready
 */

const { Telegraf, Markup } = require("telegraf");
const { connectDB } = require("./src/db");
const { getSession, updateSession, MAX_ACCOUNTS } = require("./src/session");
const {
  setCallbacks, toJid, getStatus, getPhone, getAllStatuses, getConnectedCount,
  connectAccount, disconnectAccount, getAllGroups,
  getGroupMembers, getGroupPendingRequests,
  promoteParticipant, demoteParticipant, acceptJoinRequest,
  startAutoAccept, stopAutoAccept, isAutoAcceptActive, getAutoAcceptConfig,
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
const fmtMs = (ms) => {
  if (ms < 60000) return `${ms / 1000}s`;
  if (ms < 3600000) return `${ms / 60000} min`;
  return `${ms / 3600000} ghante`;
};

// ─── Main Menu ─────────────────────────────────────────────────────────
function mainMenu() {
  const n = getConnectedCount();
  return Markup.inlineKeyboard([
    [Markup.button.callback(`📱 Accounts (${n}/${MAX_ACCOUNTS} connected)`, "menu_accounts")],
    [Markup.button.callback("👥 Group Manager", "menu_group_manager")],
    [Markup.button.callback("📊 Status", "menu_status")],
  ]);
}

async function sendMainMenu(ctx, text) {
  await ctx.reply(
    text || "👋 *WhatsApp Group Manager Bot*\n\nMenu se option chunein:",
    { parse_mode: "Markdown", ...mainMenu() },
  );
}

// ─── Accounts keyboard ─────────────────────────────────────────────────
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
    { parse_mode: "Markdown", ...mainMenu() },
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

// ─── Status ─────────────────────────────────────────────────────────────
bot.action("menu_status", async (ctx) => {
  await ctx.answerCbQuery();
  const statuses = getAllStatuses();
  const waLines = statuses.map((a) =>
    `${se(a.status)} Acc${a.index+1}${a.phone ? ` — \`${a.phone}\`` : " — Disconnected"}`
  ).join("\n");

  await ctx.reply(
    `📊 *Status*\n\n*WhatsApp Accounts:*\n${waLines}`,
    { parse_mode: "Markdown", ...Markup.inlineKeyboard([[Markup.button.callback("🔙 Main Menu", "back_menu")]])},
  );
});

// ═══════════════════════════════════════════════════════════════════════
//  GROUP MANAGER
// ═══════════════════════════════════════════════════════════════════════

// ─── Step 1: Select account ────────────────────────────────────────────
bot.action("menu_group_manager", async (ctx) => {
  await ctx.answerCbQuery();
  const connected = getAllStatuses().filter((a) => a.status === "connected");

  if (!connected.length) {
    await ctx.reply(
      "❌ *Koi account connected nahi!*\nPehle ek account connect karein.",
      { parse_mode: "Markdown", ...Markup.inlineKeyboard([
        [Markup.button.callback("📱 Accounts", "menu_accounts")],
        [Markup.button.callback("🔙 Main Menu", "back_menu")],
      ])},
    );
    return;
  }

  const rows = connected.map((a) => [
    Markup.button.callback(`✅ Account ${a.index + 1} — ${a.phone.slice(-5)}`, `gm_acc_${a.index}`),
  ]);
  rows.push([Markup.button.callback("🔙 Main Menu", "back_menu")]);

  await ctx.reply(
    "👥 *Group Manager*\n\nKaunse account ke groups manage karne hain?",
    { parse_mode: "Markdown", ...Markup.inlineKeyboard(rows) },
  );
});

// ─── Step 2: Show groups for account ──────────────────────────────────
bot.action(/^gm_acc_(\d+)$/, async (ctx) => {
  await ctx.answerCbQuery("Groups load ho rahe hain...");
  const accIdx = parseInt(ctx.match[1]);
  const phone = getPhone(accIdx);

  const loadMsg = await ctx.reply("⏳ Groups load ho rahe hain...");
  const groups = await getAllGroups(accIdx);
  try { await ctx.telegram.deleteMessage(ctx.chat.id, loadMsg.message_id); } catch {}

  if (!groups.length) {
    await ctx.reply(
      `❌ Account ${accIdx + 1} mein koi group nahi mila.`,
      Markup.inlineKeyboard([[Markup.button.callback("🔙 Account Select", "menu_group_manager")]]),
    );
    return;
  }

  updateSession(ctx.from.id, { gmAccIdx: accIdx, gmGroups: groups });

  const GROUPS_PER_PAGE = 8;
  await showGroupsPage(ctx, accIdx, groups, 0, phone);
});

async function showGroupsPage(ctx, accIdx, groups, page, phone) {
  const GROUPS_PER_PAGE = 8;
  const start = page * GROUPS_PER_PAGE;
  const slice = groups.slice(start, start + GROUPS_PER_PAGE);
  const totalPages = Math.ceil(groups.length / GROUPS_PER_PAGE);

  const rows = slice.map((g, i) => {
    const shortName = g.name.length > 28 ? g.name.slice(0, 26) + "…" : g.name;
    return [Markup.button.callback(shortName, `gm_grp_${accIdx}_${start + i}`)];
  });

  const navRow = [];
  if (page > 0) navRow.push(Markup.button.callback("⬅️ Pehle", `gm_page_${accIdx}_${page - 1}`));
  if (page < totalPages - 1) navRow.push(Markup.button.callback("Aage ➡️", `gm_page_${accIdx}_${page + 1}`));
  if (navRow.length) rows.push(navRow);
  rows.push([Markup.button.callback("🔙 Account Select", "menu_group_manager")]);

  const text = `👥 *Groups — Account ${accIdx + 1}* (\`${phone.slice(-5)}\`)\n` +
    `${groups.length} groups | Page ${page + 1}/${totalPages}\n\nGroup chunein:`;

  await ctx.reply(text, { parse_mode: "Markdown", ...Markup.inlineKeyboard(rows) });
}

bot.action(/^gm_page_(\d+)_(\d+)$/, async (ctx) => {
  await ctx.answerCbQuery();
  const accIdx = parseInt(ctx.match[1]);
  const page = parseInt(ctx.match[2]);
  const s = getSession(ctx.from.id);
  const groups = s.gmGroups || [];
  const phone = getPhone(accIdx);
  await showGroupsPage(ctx, accIdx, groups, page, phone);
});

// ─── Step 3: Group action menu ─────────────────────────────────────────
bot.action(/^gm_grp_(\d+)_(\d+)$/, async (ctx) => {
  await ctx.answerCbQuery();
  const accIdx = parseInt(ctx.match[1]);
  const grpIdx = parseInt(ctx.match[2]);
  const s = getSession(ctx.from.id);
  const groups = s.gmGroups || [];
  const group = groups[grpIdx];

  if (!group) {
    await ctx.reply("❌ Group nahi mila. Dobara try karein.", Markup.inlineKeyboard([[Markup.button.callback("🔙 Wapas", "menu_group_manager")]]));
    return;
  }

  updateSession(ctx.from.id, { gmGroupId: group.id, gmGroupName: group.name, gmAccIdx: accIdx });

  const autoActive = isAutoAcceptActive(accIdx, group.id);
  const autoConf = getAutoAcceptConfig(accIdx, group.id);

  const shortName = group.name.length > 30 ? group.name.slice(0, 28) + "…" : group.name;

  await ctx.reply(
    `👥 *${shortName}*\n\nKya karna hai?`,
    { parse_mode: "Markdown", ...Markup.inlineKeyboard([
      [Markup.button.callback("📋 Member List", `gm_members_${accIdx}`), Markup.button.callback("⏳ Pending Requests", `gm_pending_${accIdx}`)],
      [Markup.button.callback("⬆️ Admin Banao", `gm_promote_${accIdx}`), Markup.button.callback("⬇️ Admin Hatao", `gm_demote_${accIdx}`)],
      [Markup.button.callback(
        autoActive ? `🤖 AI Auto-Accept ✅ (${fmtMs(autoConf?.intervalMs || 60000)})` : "🤖 AI Auto-Accept ❌",
        `gm_auto_${accIdx}`,
      )],
      [Markup.button.callback("🔙 Groups", `gm_acc_${accIdx}`)],
    ])},
  );
});

// ─── Member List ───────────────────────────────────────────────────────
bot.action(/^gm_members_(\d+)$/, async (ctx) => {
  await ctx.answerCbQuery("Members load ho rahe hain...");
  const accIdx = parseInt(ctx.match[1]);
  const s = getSession(ctx.from.id);
  const groupId = s.gmGroupId;
  const groupName = s.gmGroupName || "Group";

  if (!groupId) { await ctx.reply("❌ Group select nahi hai."); return; }

  const loadMsg = await ctx.reply("⏳ Members load ho rahe hain...");
  const members = await getGroupMembers(accIdx, groupId);
  try { await ctx.telegram.deleteMessage(ctx.chat.id, loadMsg.message_id); } catch {}

  if (!members.length) {
    await ctx.reply(`❌ Members nahi mile — ya bot ko access nahi.`,
      Markup.inlineKeyboard([[Markup.button.callback("🔙 Wapas", `gm_grp_${accIdx}_0`)]]));
    return;
  }

  const admins = members.filter((m) => m.admin);
  const regular = members.filter((m) => !m.admin);

  let text = `📋 *Members — ${groupName}*\nTotal: ${members.length}\n\n`;
  if (admins.length) {
    text += `*Admins (${admins.length}):*\n`;
    text += admins.map((m) => `👑 \`${m.number}\`${m.superadmin ? " (Owner)" : ""}`).join("\n");
    text += "\n\n";
  }
  text += `*Members (${regular.length}):*\n`;

  // Telegram message limit — split into chunks of 30
  const chunks = [];
  let chunk = text;
  for (let i = 0; i < regular.length; i++) {
    const line = `👤 \`${regular[i].number}\`\n`;
    if ((chunk + line).length > 3800) {
      chunks.push(chunk);
      chunk = "";
    }
    chunk += line;
  }
  chunks.push(chunk);

  for (let i = 0; i < chunks.length; i++) {
    const isLast = i === chunks.length - 1;
    await ctx.reply(chunks[i], {
      parse_mode: "Markdown",
      ...(isLast ? Markup.inlineKeyboard([[Markup.button.callback("🔙 Group Menu", `gm_grp_${accIdx}_${s.gmGroups?.findIndex((g) => g.id === groupId) ?? 0}`)]]) : {}),
    });
  }
});

// ─── Pending Requests ──────────────────────────────────────────────────
bot.action(/^gm_pending_(\d+)$/, async (ctx) => {
  await ctx.answerCbQuery("Pending requests load ho rahe hain...");
  const accIdx = parseInt(ctx.match[1]);
  const s = getSession(ctx.from.id);
  const groupId = s.gmGroupId;
  const groupName = s.gmGroupName || "Group";

  if (!groupId) { await ctx.reply("❌ Group select nahi hai."); return; }

  const loadMsg = await ctx.reply("⏳ Pending requests load ho rahe hain...");
  const pending = await getGroupPendingRequests(accIdx, groupId);
  try { await ctx.telegram.deleteMessage(ctx.chat.id, loadMsg.message_id); } catch {}

  const grpIdx = s.gmGroups?.findIndex((g) => g.id === groupId) ?? 0;

  if (!pending.length) {
    await ctx.reply(
      `⏳ *Pending Requests — ${groupName}*\n\n✅ Koi pending request nahi hai!`,
      { parse_mode: "Markdown", ...Markup.inlineKeyboard([[Markup.button.callback("🔙 Group Menu", `gm_grp_${accIdx}_${grpIdx}`)]]) },
    );
    return;
  }

  let text = `⏳ *Pending Requests — ${groupName}*\nTotal: ${pending.length}\n\n`;
  const lines = pending.map((p) => `📩 \`${p.number}\``).join("\n");

  await ctx.reply(text + lines, {
    parse_mode: "Markdown",
    ...Markup.inlineKeyboard([[Markup.button.callback("🔙 Group Menu", `gm_grp_${accIdx}_${grpIdx}`)]]),
  });
});

// ─── Promote to Admin ──────────────────────────────────────────────────
bot.action(/^gm_promote_(\d+)$/, async (ctx) => {
  await ctx.answerCbQuery();
  const accIdx = parseInt(ctx.match[1]);
  const s = getSession(ctx.from.id);
  const groupName = s.gmGroupName || "Group";

  updateSession(ctx.from.id, {
    awaitingNumberForAction: "promote",
    gmAccIdx: accIdx,
  });

  await ctx.reply(
    `⬆️ *Admin Banao — ${groupName}*\n\n` +
    `Jo number admin banana hai uska phone number bhejein\n` +
    `(country code ke saath, example: \`919876543210\`)\n\n` +
    `_Bot pehle members mein dhundhega, agar nahi mila to pending requests mein check karega — accept karke admin banayega_`,
    { parse_mode: "Markdown", ...Markup.inlineKeyboard([[Markup.button.callback("❌ Cancel", `gm_acc_${accIdx}`)]]) },
  );
});

// ─── Demote Admin ──────────────────────────────────────────────────────
bot.action(/^gm_demote_(\d+)$/, async (ctx) => {
  await ctx.answerCbQuery();
  const accIdx = parseInt(ctx.match[1]);
  const s = getSession(ctx.from.id);
  const groupName = s.gmGroupName || "Group";

  updateSession(ctx.from.id, {
    awaitingNumberForAction: "demote",
    gmAccIdx: accIdx,
  });

  await ctx.reply(
    `⬇️ *Admin Hatao — ${groupName}*\n\n` +
    `Jo number admin se hatana hai uska phone number bhejein\n` +
    `(country code ke saath, example: \`919876543210\`)\n\n` +
    `_Bot members mein dhundhega aur admin se demote karega_`,
    { parse_mode: "Markdown", ...Markup.inlineKeyboard([[Markup.button.callback("❌ Cancel", `gm_acc_${accIdx}`)]]) },
  );
});

// ─── AI Auto-Accept settings ───────────────────────────────────────────
bot.action(/^gm_auto_(\d+)$/, async (ctx) => {
  await ctx.answerCbQuery();
  const accIdx = parseInt(ctx.match[1]);
  const s = getSession(ctx.from.id);
  const groupId = s.gmGroupId;
  const groupName = s.gmGroupName || "Group";
  const grpIdx = s.gmGroups?.findIndex((g) => g.id === groupId) ?? 0;

  const autoActive = isAutoAcceptActive(accIdx, groupId);
  const autoConf = getAutoAcceptConfig(accIdx, groupId);

  if (autoActive) {
    // Show status + option to stop
    await ctx.reply(
      `🤖 *AI Auto-Accept — ${groupName}*\n\n` +
      `Status: *🟢 Active*\n` +
      `Interval: *${fmtMs(autoConf?.intervalMs || 60000)}* mein check\n\n` +
      `_Sirf join link se aane wali requests accept hoti hain_\n` +
      `_(Kisi member ke add karne par aane wali requests nahi)_`,
      { parse_mode: "Markdown", ...Markup.inlineKeyboard([
        [Markup.button.callback("🛑 Auto-Accept Band Karo", `gm_auto_stop_${accIdx}`)],
        [Markup.button.callback("🔙 Group Menu", `gm_grp_${accIdx}_${grpIdx}`)],
      ])},
    );
  } else {
    // Show interval selection to start
    await ctx.reply(
      `🤖 *AI Auto-Accept — ${groupName}*\n\n` +
      `Status: *🔴 Inactive*\n\n` +
      `_Kitne time baad join requests check karein?_\n` +
      `_(Sirf join link wale requests accept honge — member-added nahi)_`,
      { parse_mode: "Markdown", ...Markup.inlineKeyboard([
        [
          Markup.button.callback("30 sec", `gm_auto_start_${accIdx}_30000`),
          Markup.button.callback("1 min", `gm_auto_start_${accIdx}_60000`),
          Markup.button.callback("2 min", `gm_auto_start_${accIdx}_120000`),
        ],
        [
          Markup.button.callback("5 min", `gm_auto_start_${accIdx}_300000`),
          Markup.button.callback("10 min", `gm_auto_start_${accIdx}_600000`),
          Markup.button.callback("30 min", `gm_auto_start_${accIdx}_1800000`),
        ],
        [Markup.button.callback("🔙 Group Menu", `gm_grp_${accIdx}_${grpIdx}`)],
      ])},
    );
  }
});

bot.action(/^gm_auto_start_(\d+)_(\d+)$/, async (ctx) => {
  await ctx.answerCbQuery();
  const accIdx = parseInt(ctx.match[1]);
  const intervalMs = parseInt(ctx.match[2]);
  const s = getSession(ctx.from.id);
  const groupId = s.gmGroupId;
  const groupName = s.gmGroupName || "Group";
  const grpIdx = s.gmGroups?.findIndex((g) => g.id === groupId) ?? 0;

  if (!groupId) { await ctx.reply("❌ Group select nahi hai."); return; }

  startAutoAccept(accIdx, groupId, intervalMs);

  await ctx.editMessageText(
    `🤖 *AI Auto-Accept — ${groupName}*\n\n` +
    `Status: *🟢 Active*\n` +
    `Interval: *${fmtMs(intervalMs)}* mein check\n\n` +
    `✅ Auto-accept shuru ho gaya!\n` +
    `_Join link se aane wali saari requests automatically accept hogi_`,
    { parse_mode: "Markdown", ...Markup.inlineKeyboard([
      [Markup.button.callback("🛑 Band Karo", `gm_auto_stop_${accIdx}`)],
      [Markup.button.callback("🔙 Group Menu", `gm_grp_${accIdx}_${grpIdx}`)],
    ])},
  );
});

bot.action(/^gm_auto_stop_(\d+)$/, async (ctx) => {
  await ctx.answerCbQuery();
  const accIdx = parseInt(ctx.match[1]);
  const s = getSession(ctx.from.id);
  const groupId = s.gmGroupId;
  const groupName = s.gmGroupName || "Group";
  const grpIdx = s.gmGroups?.findIndex((g) => g.id === groupId) ?? 0;

  if (!groupId) { await ctx.reply("❌ Group select nahi hai."); return; }

  stopAutoAccept(accIdx, groupId);

  await ctx.editMessageText(
    `🤖 *AI Auto-Accept — ${groupName}*\n\n` +
    `Status: *🔴 Inactive*\n\n🛑 Auto-accept band ho gaya.`,
    { parse_mode: "Markdown", ...Markup.inlineKeyboard([
      [Markup.button.callback("🔙 Group Menu", `gm_grp_${accIdx}_${grpIdx}`)],
    ])},
  );
});

// ─── Back ──────────────────────────────────────────────────────────────
bot.action("back_menu", async (ctx) => {
  await ctx.answerCbQuery();
  updateSession(ctx.from.id, { awaitingPhoneForIndex: null, awaitingNumberForAction: null });
  await ctx.reply("🏠 *Main Menu:*", { parse_mode: "Markdown", ...mainMenu() });
});

// ─── Text handler ──────────────────────────────────────────────────────
bot.on("text", async (ctx) => {
  const userId = ctx.from.id;
  const s = getSession(userId);
  const text = ctx.message.text.trim();
  if (text.startsWith("/")) return;

  // ── Account pairing phone number ──────────────────────────────────
  if (s.awaitingPhoneForIndex !== null && s.awaitingPhoneForIndex !== undefined) {
    const idx = s.awaitingPhoneForIndex;
    const phone = text.replace(/[^0-9]/g, "");
    if (phone.length < 10) {
      await ctx.reply("❌ Invalid number. Example: `919876543210`",
        { parse_mode: "Markdown", ...Markup.inlineKeyboard([[Markup.button.callback("🔙 Accounts", "menu_accounts")]]) });
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
            [Markup.button.callback("🔙 Accounts", "menu_accounts")],
          ])});
        return;
      }
      await ctx.reply(
        `🔑 *Pairing Code — Account ${idx+1}*\n\n\`${code}\`\n\n` +
        `*Steps:*\n1. WhatsApp open karein\n2. *Settings → Linked Devices → Link a Device*\n3. *Link with phone number* tap karein\n4. Upar ka code enter karein\n\n` +
        `⚠️ *Code sirf 60 seconds valid hai — jaldi enter karein!*\n⏳ Connect hone ka wait ho raha hai...`,
        { parse_mode: "Markdown", ...Markup.inlineKeyboard([
          [Markup.button.callback("🔄 Naya Code Mangwao", `reset_${idx}`)],
          [Markup.button.callback("🔙 Menu", "back_menu")],
        ])},
      );
    });

    pendingReadyCbs.set(idx, async () => {
      await ctx.reply(`✅ *WA Account ${idx+1} Connected!*\n📱 \`${phone}\``,
        { parse_mode: "Markdown", ...mainMenu() });
    });

    connectAccount(idx, phone).catch(async (err) => {
      pendingPairingCbs.delete(idx);
      pendingReadyCbs.delete(idx);
      await ctx.reply(`❌ Error: \`${err.message}\``,
        { parse_mode: "Markdown", ...Markup.inlineKeyboard([[Markup.button.callback("🔙 Accounts", "menu_accounts")]]) });
    });
    return;
  }

  // ── Promote / Demote number input ─────────────────────────────────
  if (s.awaitingNumberForAction) {
    const action = s.awaitingNumberForAction;
    const accIdx = s.gmAccIdx;
    const groupId = s.gmGroupId;
    const groupName = s.gmGroupName || "Group";
    const grpIdx = s.gmGroups?.findIndex((g) => g.id === groupId) ?? 0;

    const phone = text.replace(/[^0-9]/g, "");
    if (phone.length < 7) {
      await ctx.reply("❌ Invalid number. Country code ke saath dalein, example: `919876543210`",
        { parse_mode: "Markdown" });
      return;
    }

    updateSession(userId, { awaitingNumberForAction: null });

    const jid = toJid(phone);
    const waitMsg = await ctx.reply(`⏳ Processing \`${phone}\`...`, { parse_mode: "Markdown" });

    if (action === "promote") {
      // Search in members first
      const members = await getGroupMembers(accIdx, groupId);
      const found = members.find((m) => m.number === phone || m.id === jid);

      if (found) {
        if (found.admin) {
          try { await ctx.telegram.deleteMessage(ctx.chat.id, waitMsg.message_id); } catch {}
          await ctx.reply(
            `ℹ️ \`${phone}\` *pehle se admin hai!*`,
            { parse_mode: "Markdown", ...Markup.inlineKeyboard([[Markup.button.callback("🔙 Group Menu", `gm_grp_${accIdx}_${grpIdx}`)]]) },
          );
          return;
        }
        const result = await promoteParticipant(accIdx, groupId, jid);
        try { await ctx.telegram.deleteMessage(ctx.chat.id, waitMsg.message_id); } catch {}
        if (result.ok) {
          await ctx.reply(
            `✅ *\`${phone}\` ko admin bana diya!*\n👑 Group: ${groupName}`,
            { parse_mode: "Markdown", ...Markup.inlineKeyboard([[Markup.button.callback("🔙 Group Menu", `gm_grp_${accIdx}_${grpIdx}`)]]) },
          );
        } else {
          await ctx.reply(`❌ Admin banane mein error: ${result.error}`,
            Markup.inlineKeyboard([[Markup.button.callback("🔙 Group Menu", `gm_grp_${accIdx}_${grpIdx}`)]]));
        }
      } else {
        // Not in members — check pending requests
        const pending = await getGroupPendingRequests(accIdx, groupId);
        const pendingFound = pending.find((p) => p.number === phone || p.id === jid);

        if (pendingFound) {
          // Accept the request first
          const acceptResult = await acceptJoinRequest(accIdx, groupId, pendingFound.id);
          if (!acceptResult.ok) {
            try { await ctx.telegram.deleteMessage(ctx.chat.id, waitMsg.message_id); } catch {}
            await ctx.reply(`❌ Request accept karne mein error: ${acceptResult.error}`,
              Markup.inlineKeyboard([[Markup.button.callback("🔙 Group Menu", `gm_grp_${accIdx}_${grpIdx}`)]]));
            return;
          }
          // Wait a moment then promote
          await sleep(2000);
          const promoteResult = await promoteParticipant(accIdx, groupId, pendingFound.id);
          try { await ctx.telegram.deleteMessage(ctx.chat.id, waitMsg.message_id); } catch {}
          if (promoteResult.ok) {
            await ctx.reply(
              `✅ *\`${phone}\` ko accept karke admin bana diya!*\n📩 Pending request accept ki\n👑 Admin promote kiya\n🏠 Group: ${groupName}`,
              { parse_mode: "Markdown", ...Markup.inlineKeyboard([[Markup.button.callback("🔙 Group Menu", `gm_grp_${accIdx}_${grpIdx}`)]]) },
            );
          } else {
            await ctx.reply(
              `⚠️ Request accept hua par admin nahi bana saka: ${promoteResult.error}`,
              Markup.inlineKeyboard([[Markup.button.callback("🔙 Group Menu", `gm_grp_${accIdx}_${grpIdx}`)]])),
            "";
          }
        } else {
          try { await ctx.telegram.deleteMessage(ctx.chat.id, waitMsg.message_id); } catch {}
          await ctx.reply(
            `❌ *\`${phone}\` nahi mila!*\n\nNa members mein hai, na pending requests mein.\nNumber sahi hai? Country code check karein.`,
            { parse_mode: "Markdown", ...Markup.inlineKeyboard([[Markup.button.callback("🔙 Group Menu", `gm_grp_${accIdx}_${grpIdx}`)]]) },
          );
        }
      }

    } else if (action === "demote") {
      const members = await getGroupMembers(accIdx, groupId);
      const found = members.find((m) => m.number === phone || m.id === jid);

      try { await ctx.telegram.deleteMessage(ctx.chat.id, waitMsg.message_id); } catch {}

      if (!found) {
        await ctx.reply(
          `❌ *\`${phone}\` is group ka member nahi hai!*`,
          { parse_mode: "Markdown", ...Markup.inlineKeyboard([[Markup.button.callback("🔙 Group Menu", `gm_grp_${accIdx}_${grpIdx}`)]]) },
        );
        return;
      }

      if (!found.admin) {
        await ctx.reply(
          `ℹ️ *\`${phone}\` admin nahi hai!*\nSirf admins ko demote kiya ja sakta hai.`,
          { parse_mode: "Markdown", ...Markup.inlineKeyboard([[Markup.button.callback("🔙 Group Menu", `gm_grp_${accIdx}_${grpIdx}`)]]) },
        );
        return;
      }

      const result = await demoteParticipant(accIdx, groupId, jid);
      if (result.ok) {
        await ctx.reply(
          `✅ *\`${phone}\` ko admin se hata diya!*\n🏠 Group: ${groupName}`,
          { parse_mode: "Markdown", ...Markup.inlineKeyboard([[Markup.button.callback("🔙 Group Menu", `gm_grp_${accIdx}_${grpIdx}`)]]) },
        );
      } else {
        await ctx.reply(`❌ Demote karne mein error: ${result.error}`,
          Markup.inlineKeyboard([[Markup.button.callback("🔙 Group Menu", `gm_grp_${accIdx}_${grpIdx}`)]]));
      }
    }
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
    <h2>✅ WhatsApp Group Manager Bot v6</h2>
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

// ─── Main startup ────────────────────────────────────────────────────────
async function main() {
  await connectDB();
  reconnectSavedAccounts().catch((e) => console.error("[Reconnect Error]", e.message));
  await bot.launch({ dropPendingUpdates: true });
  console.log(`✅ Bot v6 running! Owner: ${OWNER_ID || "NOT SET"} | Max accounts: ${MAX_ACCOUNTS}`);
}

main().catch((err) => { console.error("❌ Fatal:", err.message); process.exit(1); });
process.once("SIGINT", () => bot.stop("SIGINT"));
process.once("SIGTERM", () => bot.stop("SIGTERM"));
