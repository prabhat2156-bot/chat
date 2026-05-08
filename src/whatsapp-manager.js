const {
  default: makeWASocket,
  useMultiFileAuthState,
  DisconnectReason,
  fetchLatestBaileysVersion,
  makeCacheableSignalKeyStore,
} = require("@whiskeysockets/baileys");
const pino = require("pino");
const { join } = require("path");
const { mkdirSync } = require("fs");

// Silent logger — Baileys bahut zyada logs karta hai
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

async function connectAccount(index, phoneNumber) {
  // Cleanup existing connection
  const acc = accounts[index];
  if (acc.socket) {
    try { acc.socket.end(); } catch {}
    acc.socket = null;
  }

  acc.status = "connecting";
  acc.phoneNumber = phoneNumber;

  const authDir = join(process.cwd(), ".wa_auth", `account${index + 1}`);
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
    mobile: false,
    browser: ["WhatsApp Broadcast Bot", "Chrome", "3.0.0"],
    syncFullHistory: false,
    generateHighQualityLinkPreview: false,
  });

  accounts[index].socket = socket;

  // Creds save karo
  socket.ev.on("creds.update", saveCreds);

  // Connection update
  socket.ev.on("connection.update", async (update) => {
    const { connection, lastDisconnect, qr } = update;

    // QR aaya — pairing code maango
    if (qr) {
      try {
        // Phone number clean karo
        const clean = phoneNumber.replace(/[^0-9]/g, "");
        await socket.requestPairingCode(clean);
      } catch (err) {
        console.error(`[WA${index + 1}] requestPairingCode error:`, err.message);
      }
    }

    if (connection === "open") {
      accounts[index].status = "connected";
      console.log(`[WA${index + 1}] ✅ Connected — ${phoneNumber}`);
      await onReady(index);
    }

    if (connection === "close") {
      const code = lastDisconnect?.error?.output?.statusCode;
      const shouldReconnect = code !== DisconnectReason.loggedOut;
      accounts[index].status = "disconnected";
      console.log(`[WA${index + 1}] Disconnected — code: ${code} — reconnect: ${shouldReconnect}`);

      if (shouldReconnect && acc.phoneNumber) {
        console.log(`[WA${index + 1}] Auto-reconnect...`);
        setTimeout(() => connectAccount(index, acc.phoneNumber).catch(console.error), 5000);
      } else {
        acc.phoneNumber = "";
        await onDisconnected(index);
      }
    }
  });

  // Pairing code event
  socket.ev.on("creds.update", async () => {
    const creds = socket.authState?.creds;
    if (creds?.myAppStateKeyId && acc.status === "connecting") {
      // Connected via pairing
    }
  });

  // Pairing code listener — Baileys sends it via this
  const origRequestPairingCode = socket.requestPairingCode.bind(socket);
  let pairingCodeSent = false;
  socket.requestPairingCode = async (phone) => {
    const code = await origRequestPairingCode(phone);
    if (code && !pairingCodeSent) {
      pairingCodeSent = true;
      await onPairingCode(index, code);
    }
    return code;
  };
}

async function disconnectAccount(index) {
  const acc = accounts[index];
  if (acc.socket) {
    try { acc.socket.end(undefined); } catch {}
    acc.socket = null;
  }
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
