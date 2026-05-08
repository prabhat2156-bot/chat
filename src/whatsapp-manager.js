const {
  default: makeWASocket,
  useMultiFileAuthState,
  DisconnectReason,
  fetchLatestBaileysVersion,
  makeCacheableSignalKeyStore,
} = require("@whiskeysockets/baileys");
const pino = require("pino");
const { join } = require("path");
const { mkdirSync, rmSync, existsSync } = require("fs");

const logger = pino({ level: "silent" });

const accounts = [
  { socket: null, status: "disconnected", phoneNumber: "", groups: [] },
  { socket: null, status: "disconnected", phoneNumber: "", groups: [] },
];

let onPairingCode = async () => {};
let onReady = async () => {};
let onDisconnected = async () => {};

function setCallbacks(opts) {
  if (opts.onPairingCode) onPairingCode = opts.onPairingCode;
  if (opts.onReady) onReady = opts.onReady;
  if (opts.onDisconnected) onDisconnected = opts.onDisconnected;
}

function getStatus(index) { return accounts[index].status; }
function getPhone(index) { return accounts[index].phoneNumber; }

function getAuthDir(index) {
  return join(process.cwd(), ".wa_auth", `account${index + 1}`);
}

// Auth files saaf karo (fresh start ke liye)
function clearAuth(index) {
  const dir = getAuthDir(index);
  if (existsSync(dir)) {
    try { rmSync(dir, { recursive: true, force: true }); } catch {}
    console.log(`[WA${index + 1}] Auth cleared`);
  }
}

async function connectAccount(index, phoneNumber, freshStart = true) {
  const acc = accounts[index];

  // Purani connection band karo
  if (acc.socket) {
    try { acc.socket.end(undefined); } catch {}
    acc.socket = null;
  }

  // Fresh start = purana auth hata do (naya pairing ke liye)
  if (freshStart) clearAuth(index);

  acc.status = "connecting";
  acc.phoneNumber = phoneNumber;

  const authDir = getAuthDir(index);
  mkdirSync(authDir, { recursive: true });

  const { state, saveCreds } = await useMultiFileAuthState(authDir);
  const { version } = await fetchLatestBaileysVersion();

  const socket = makeWASocket({
    version,
    logger,
    auth: {
      creds: state.creds,
      keys: makeCacheableSignalKeyStore(state.keys, logger),
    },
    printQRInTerminal: false,
    browser: ["Chrome (Linux)", "Chrome", "120.0.0"],
    syncFullHistory: false,
    generateHighQualityLinkPreview: false,
    connectTimeoutMs: 60000,
    defaultQueryTimeoutMs: 60000,
    keepAliveIntervalMs: 10000,
  });

  accounts[index].socket = socket;

  socket.ev.on("creds.update", saveCreds);

  let pairingRequested = false;

  socket.ev.on("connection.update", async (update) => {
    const { connection, lastDisconnect, qr } = update;

    // QR aane ka matlab — socket ready hai, pairing code maango
    if (qr && !pairingRequested) {
      pairingRequested = true;
      try {
        const clean = phoneNumber.replace(/[^0-9]/g, "");
        console.log(`[WA${index + 1}] Requesting pairing code for ${clean}...`);
        const code = await socket.requestPairingCode(clean);
        if (code) {
          console.log(`[WA${index + 1}] Pairing code: ${code}`);
          await onPairingCode(index, code);
        }
      } catch (err) {
        console.error(`[WA${index + 1}] Pairing code error:`, err.message);
        // Retry after 3 sec
        setTimeout(async () => {
          try {
            const clean = phoneNumber.replace(/[^0-9]/g, "");
            const code = await socket.requestPairingCode(clean);
            if (code) await onPairingCode(index, code);
          } catch (e) {
            console.error(`[WA${index + 1}] Pairing retry failed:`, e.message);
          }
        }, 3000);
      }
    }

    if (connection === "open") {
      acc.status = "connected";
      console.log(`[WA${index + 1}] ✅ Connected — ${phoneNumber}`);
      await onReady(index);
    }

    if (connection === "close") {
      const code = lastDisconnect?.error?.output?.statusCode;
      const loggedOut = code === DisconnectReason.loggedOut;
      acc.status = "disconnected";
      console.log(`[WA${index + 1}] Disconnected — reason code: ${code}`);

      if (loggedOut) {
        // Logout hua — auth clear karo
        clearAuth(index);
        acc.phoneNumber = "";
        await onDisconnected(index);
      } else if (acc.phoneNumber) {
        // Normal disconnect — auto-reconnect (auth keep karo)
        console.log(`[WA${index + 1}] Reconnecting in 5s...`);
        setTimeout(() => {
          connectAccount(index, acc.phoneNumber, false).catch(console.error);
        }, 5000);
      }
    }
  });
}

async function disconnectAccount(index) {
  const acc = accounts[index];
  if (acc.socket) {
    try { acc.socket.end(undefined); } catch {}
    acc.socket = null;
  }
  clearAuth(index);
  acc.status = "disconnected";
  acc.phoneNumber = "";
  acc.groups = [];
}

async function getAllGroups(index) {
  const acc = accounts[index];
  if (!acc.socket || acc.status !== "connected") return [];
  try {
    const groups = await acc.socket.groupFetchAllParticipating();
    return Object.entries(groups).map(([id, g]) => ({
      id,
      name: g.subject || id,
    }));
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

module.exports = {
  setCallbacks, getStatus, getPhone,
  connectAccount, disconnectAccount,
  getAllGroups, sendMessageToGroup,
};
