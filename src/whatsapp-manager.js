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
  status: "disconnected", // disconnected | connecting | connected
  phoneNumber: "",
}));

let onPairingCode = async () => {};
let onReady = async () => {};
let onDisconnected = async () => {};

function setCallbacks(opts) {
  if (opts.onPairingCode) onPairingCode = opts.onPairingCode;
  if (opts.onReady) onReady = opts.onReady;
  if (opts.onDisconnected) onDisconnected = opts.onDisconnected;
}

function getStatus(index) { return accounts[index]?.status ?? "disconnected"; }
function getPhone(index) { return accounts[index]?.phoneNumber ?? ""; }
function getAllStatuses() { return accounts.map((a) => ({ index: a.index, status: a.status, phone: a.phoneNumber })); }
function getConnectedCount() { return accounts.filter((a) => a.status === "connected").length; }

async function connectAccount(index, phoneNumber, freshStart = true) {
  if (index < 0 || index >= MAX_ACCOUNTS) throw new Error("Invalid account index");
  const acc = accounts[index];

  // Close existing socket
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

    // QR fires first → immediately request pairing code instead
    if (qr && !pairingRequested) {
      pairingRequested = true;
      await _requestPairingWithRetry(socket, index, clean);
    }

    if (connection === "open") {
      acc.status = "connected";
      // Mark auth as saved in MongoDB
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
        // Auto-reconnect with saved auth (no fresh pairing)
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

// Reconnect all accounts that have saved auth in MongoDB (called on startup)
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
  setCallbacks, getStatus, getPhone, getAllStatuses, getConnectedCount,
  connectAccount, disconnectAccount, getAllGroups, sendMessageToGroup,
  reconnectSavedAccounts,
};
