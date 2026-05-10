const {
  default: makeWASocket,
  DisconnectReason,
  fetchLatestBaileysVersion,
} = require("@whiskeysockets/baileys");
const pino = require("pino");
const { useMongoAuthState, clearMongoAuth } = require("./mongoAuthState");
const { AccountInfo } = require("./models");

const logger = pino({ level: "silent" });
const MAX_ACCOUNTS = 10;

const accounts = Array.from({ length: MAX_ACCOUNTS }, (_, i) => ({
  index: i,
  socket: null,
  status: "disconnected",
  phoneNumber: "",
}));

let onPairingCode = async () => {};
let onReady = async () => {};
let onDisconnected = async () => {};

// ─── Auto-accept timers: key = `${accountIndex}_${groupId}` ────────────
const autoAcceptTimers = new Map();
const autoAcceptConfigs = new Map();

function setCallbacks(opts) {
  if (opts.onPairingCode) onPairingCode = opts.onPairingCode;
  if (opts.onReady) onReady = opts.onReady;
  if (opts.onDisconnected) onDisconnected = opts.onDisconnected;
}

function getStatus(index) { return accounts[index]?.status ?? "disconnected"; }
function getPhone(index) { return accounts[index]?.phoneNumber ?? ""; }
function getAllStatuses() { return accounts.map((a) => ({ index: a.index, status: a.status, phone: a.phoneNumber })); }
function getConnectedCount() { return accounts.filter((a) => a.status === "connected").length; }

// ─── Normalize number to WhatsApp JID ──────────────────────────────────
function toJid(number) {
  const clean = number.replace(/[^0-9]/g, "");
  return `${clean}@s.whatsapp.net`;
}

// ─── Flexible number match (handles missing country code) ───────────────
// e.g. stored: "919876543210", entered: "9876543210" → still matches (suffix)
function numberMatches(stored, input) {
  if (!stored || !input) return false;
  const s = stored.replace(/[^0-9]/g, "");
  const i = input.replace(/[^0-9]/g, "");
  if (s === i) return true;
  if (s.endsWith(i) && i.length >= 8) return true;
  if (i.endsWith(s) && s.length >= 8) return true;
  return false;
}

async function connectAccount(index, phoneNumber, freshStart = true) {
  if (index < 0 || index >= MAX_ACCOUNTS) throw new Error("Invalid account index");
  const acc = accounts[index];

  if (acc.socket) {
    try { acc.socket.end(undefined); } catch {}
    acc.socket = null;
  }

  const accountId = `account${index + 1}`;
  if (freshStart) {
    await clearMongoAuth(accountId);
    await AccountInfo.findOneAndUpdate(
      { accountIndex: index },
      { accountIndex: index, phoneNumber, hasAuth: false },
      { upsert: true }
    );
  }

  acc.status = "connecting";
  acc.phoneNumber = phoneNumber;

  const { state, saveCreds } = await useMongoAuthState(accountId);
  const { version } = await fetchLatestBaileysVersion();

  const socket = makeWASocket({
    version,
    logger,
    auth: state,
    printQRInTerminal: false,
    browser: ["Ubuntu", "Chrome", "120.0.0.0"],
    syncFullHistory: false,
    generateHighQualityLinkPreview: false,
    connectTimeoutMs: 60000,
    defaultQueryTimeoutMs: 60000,
    keepAliveIntervalMs: 15000,
    markOnlineOnConnect: false,
  });

  acc.socket = socket;
  socket.ev.on("creds.update", saveCreds);

  const clean = phoneNumber.replace(/[^0-9]/g, "");
  let pairingRequested = false;

  socket.ev.on("connection.update", async (update) => {
    const { connection, lastDisconnect, qr } = update;

    if (qr && !pairingRequested) {
      pairingRequested = true;
      await _requestPairingWithRetry(socket, index, clean);
    }

    if (connection === "open") {
      acc.status = "connected";
      await AccountInfo.findOneAndUpdate(
        { accountIndex: index },
        { accountIndex: index, phoneNumber: clean, hasAuth: true },
        { upsert: true }
      );
      console.log(`[WA${index + 1}] ✅ Connected — ${clean}`);
      await onReady(index);
    }

    if (connection === "close") {
      const code = lastDisconnect?.error?.output?.statusCode;
      const loggedOut = code === DisconnectReason.loggedOut;
      acc.status = "disconnected";
      console.log(`[WA${index + 1}] Disconnected — code: ${code}`);

      if (loggedOut) {
        await clearMongoAuth(accountId);
        await AccountInfo.findOneAndUpdate(
          { accountIndex: index },
          { accountIndex: index, phoneNumber: "", hasAuth: false },
          { upsert: true }
        );
        acc.phoneNumber = "";
        await onDisconnected(index);
      } else if (acc.phoneNumber) {
        console.log(`[WA${index + 1}] Reconnecting in 5s...`);
        setTimeout(() => {
          connectAccount(index, acc.phoneNumber, false).catch(console.error);
        }, 5000);
      }
    }
  });
}

async function _requestPairingWithRetry(socket, index, clean, attempt = 1) {
  try {
    console.log(`[WA${index + 1}] Requesting pairing code... (attempt ${attempt})`);
    const code = await socket.requestPairingCode(clean);
    if (code) {
      const formatted = code.replace(/[^A-Z0-9]/gi, "").match(/.{1,4}/g)?.join("-") ?? code;
      console.log(`[WA${index + 1}] Pairing code: ${formatted}`);
      await onPairingCode(index, formatted);
    }
  } catch (err) {
    console.error(`[WA${index + 1}] Pairing error (attempt ${attempt}):`, err.message);
    if (attempt < 3) {
      await new Promise((r) => setTimeout(r, 4000));
      await _requestPairingWithRetry(socket, index, clean, attempt + 1);
    } else {
      await onPairingCode(index, null);
    }
  }
}

async function disconnectAccount(index) {
  const acc = accounts[index];
  if (acc.socket) {
    try { acc.socket.end(undefined); } catch {}
    acc.socket = null;
  }
  const accountId = `account${index + 1}`;
  await clearMongoAuth(accountId);
  await AccountInfo.findOneAndUpdate(
    { accountIndex: index },
    { accountIndex: index, phoneNumber: "", hasAuth: false },
    { upsert: true }
  );
  acc.status = "disconnected";
  acc.phoneNumber = "";
}

async function getAllGroups(index) {
  const acc = accounts[index];
  if (!acc.socket || acc.status !== "connected") return [];
  try {
    const groups = await acc.socket.groupFetchAllParticipating();
    return Object.entries(groups).map(([id, g]) => ({ id, name: g.subject || id }));
  } catch (err) {
    console.error(`[WA${index + 1}] getAllGroups error:`, err.message);
    return [];
  }
}

// ─── Get group members with admin info ─────────────────────────────────
async function getGroupMembers(index, groupId) {
  const acc = accounts[index];
  if (!acc.socket || acc.status !== "connected") return [];
  try {
    const meta = await acc.socket.groupMetadata(groupId);
    return (meta.participants || []).map((p) => ({
      id: p.id,
      // Strip device suffix (:5) — JID format: number:device@s.whatsapp.net
      number: p.id.split("@")[0].split(":")[0],
      admin: p.admin === "admin" || p.admin === "superadmin",
      superadmin: p.admin === "superadmin",
    }));
  } catch (err) {
    console.error(`[WA${index + 1}] getGroupMembers error:`, err.message);
    return [];
  }
}

// ─── Get pending join requests ──────────────────────────────────────────
// Returns { id, number, method, error? }
// method: "invite_link" = join link | "non_admin_add" = added by member
async function getGroupPendingRequests(index, groupId) {
  const acc = accounts[index];
  if (!acc.socket || acc.status !== "connected") return { list: [], error: "Not connected" };

  const parseEntry = (p, defaultMethod) => {
    const jid = typeof p === "string" ? p : (p.jid || p.id || String(p));
    const number = jid.split("@")[0].split(":")[0];
    const method = (typeof p === "object" && p !== null)
      ? (p.method || p.requestMethod || defaultMethod)
      : defaultMethod;
    return { id: jid, number, method };
  };

  let results = [];
  let errorMsg = null;

  // Primary: groupRequestParticipantsList (link-join requests)
  try {
    const list = await acc.socket.groupRequestParticipantsList(groupId);
    if (Array.isArray(list)) {
      results.push(...list.map((p) => parseEntry(p, "invite_link")));
    }
  } catch (err) {
    errorMsg = err.message;
    console.error(`[WA${index + 1}] groupRequestParticipantsList error:`, err.message);
  }

  // Fallback: groupMetadata.pendingParticipants (member-added requests)
  try {
    const meta = await acc.socket.groupMetadata(groupId);
    const pending = meta.pendingParticipants || [];
    for (const p of pending) {
      const entry = parseEntry(p, "non_admin_add");
      // Avoid duplicates
      if (!results.find((r) => r.id === entry.id)) {
        results.push(entry);
      }
    }
  } catch (err) {
    console.error(`[WA${index + 1}] groupMetadata pendingParticipants error:`, err.message);
  }

  return { list: results, error: results.length === 0 ? errorMsg : null };
}

// ─── Promote participant to admin ──────────────────────────────────────
async function promoteParticipant(index, groupId, jid) {
  const acc = accounts[index];
  if (!acc.socket || acc.status !== "connected") return { ok: false, error: "Not connected" };
  try {
    await acc.socket.groupParticipantsUpdate(groupId, [jid], "promote");
    return { ok: true };
  } catch (err) {
    console.error(`[WA${index + 1}] promoteParticipant error:`, err.message);
    return { ok: false, error: err.message };
  }
}

// ─── Demote admin ──────────────────────────────────────────────────────
async function demoteParticipant(index, groupId, jid) {
  const acc = accounts[index];
  if (!acc.socket || acc.status !== "connected") return { ok: false, error: "Not connected" };
  try {
    await acc.socket.groupParticipantsUpdate(groupId, [jid], "demote");
    return { ok: true };
  } catch (err) {
    console.error(`[WA${index + 1}] demoteParticipant error:`, err.message);
    return { ok: false, error: err.message };
  }
}

// ─── Accept a link-join request ─────────────────────────────────────────
async function acceptJoinRequest(index, groupId, jid) {
  const acc = accounts[index];
  if (!acc.socket || acc.status !== "connected") return { ok: false, error: "Not connected" };
  try {
    await acc.socket.groupRequestParticipantsUpdate(groupId, [jid], "approve");
    return { ok: true };
  } catch (err) {
    console.error(`[WA${index + 1}] acceptJoinRequest error:`, err.message);
    return { ok: false, error: err.message };
  }
}

// ─── Auto-accept join requests for a group ─────────────────────────────
// key = `${accountIndex}_${groupId}`
function autoAcceptKey(accountIndex, groupId) {
  return `${accountIndex}_${groupId}`;
}

function startAutoAccept(accountIndex, groupId, intervalMs) {
  const key = autoAcceptKey(accountIndex, groupId);
  if (autoAcceptTimers.has(key)) {
    clearInterval(autoAcceptTimers.get(key));
    autoAcceptTimers.delete(key);
  }

  autoAcceptConfigs.set(key, { accountIndex, groupId, intervalMs, startedAt: Date.now() });

  const timer = setInterval(async () => {
    try {
      const { list } = await getGroupPendingRequests(accountIndex, groupId);
      // Only accept join-link requests — skip member-added (non_admin_add) ones
      const linkOnly = list.filter((r) => r.method === "invite_link" || r.method === "unknown");
      for (const req of linkOnly) {
        const result = await acceptJoinRequest(accountIndex, groupId, req.id);
        if (result.ok) {
          console.log(`[AutoAccept] Accepted ${req.number} (${req.method}) in group ${groupId}`);
        }
        await new Promise((r) => setTimeout(r, 1000));
      }
    } catch (err) {
      console.error(`[AutoAccept] Error for ${key}:`, err.message);
    }
  }, intervalMs);

  autoAcceptTimers.set(key, timer);
  return key;
}

function stopAutoAccept(accountIndex, groupId) {
  const key = autoAcceptKey(accountIndex, groupId);
  if (autoAcceptTimers.has(key)) {
    clearInterval(autoAcceptTimers.get(key));
    autoAcceptTimers.delete(key);
    autoAcceptConfigs.delete(key);
    return true;
  }
  return false;
}

function isAutoAcceptActive(accountIndex, groupId) {
  return autoAcceptTimers.has(autoAcceptKey(accountIndex, groupId));
}

function getAutoAcceptConfig(accountIndex, groupId) {
  return autoAcceptConfigs.get(autoAcceptKey(accountIndex, groupId)) || null;
}

function getAllAutoAcceptConfigs() {
  return [...autoAcceptConfigs.values()];
}

async function sendMessageToGroup(index, groupId, message) {
  const acc = accounts[index];
  if (!acc.socket || acc.status !== "connected") return false;
  try {
    await acc.socket.sendMessage(groupId, { text: message });
    return true;
  } catch (err) {
    console.error(`[WA${index + 1}] sendMessage error:`, err.message);
    return false;
  }
}

async function reconnectSavedAccounts() {
  const savedAccounts = await AccountInfo.find({ hasAuth: true });
  if (!savedAccounts.length) return;
  console.log(`[Startup] Reconnecting ${savedAccounts.length} saved account(s)...`);
  await Promise.allSettled(
    savedAccounts.map((ai) =>
      connectAccount(ai.accountIndex, ai.phoneNumber, false).catch((e) =>
        console.error(`[Startup] Account ${ai.accountIndex + 1} reconnect failed:`, e.message)
      )
    )
  );
}

module.exports = {
  MAX_ACCOUNTS,
  toJid, numberMatches,
  setCallbacks, getStatus, getPhone, getAllStatuses, getConnectedCount,
  connectAccount, disconnectAccount, getAllGroups, sendMessageToGroup,
  getGroupMembers, getGroupPendingRequests,
  promoteParticipant, demoteParticipant, acceptJoinRequest,
  startAutoAccept, stopAutoAccept, isAutoAcceptActive, getAutoAcceptConfig, getAllAutoAcceptConfigs,
  reconnectSavedAccounts,
};
