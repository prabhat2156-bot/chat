const { Client, LocalAuth } = require("whatsapp-web.js");
const { execSync } = require("child_process");
const { existsSync } = require("fs");

// Render + Linux + local sab ke liye Chromium dhundho
function findChromium() {
  // 1. Manual env variable
  const env = process.env.CHROMIUM_PATH;
  if (env && existsSync(env)) return env;

  // 2. System chromium (Linux VPS / Replit)
  try {
    const found = execSync(
      "which chromium || which chromium-browser || which google-chrome-stable || which google-chrome 2>/dev/null",
      { encoding: "utf8", stdio: ["pipe", "pipe", "ignore"] }
    ).trim();
    if (found && existsSync(found)) return found;
  } catch {}

  // 3. Puppeteer ka bundled Chromium (Render pe yahi kaam karta hai)
  try {
    const puppeteer = require("puppeteer");
    const execPath = puppeteer.executablePath();
    if (execPath && existsSync(execPath)) {
      console.log("[WA] Puppeteer bundled Chromium use ho raha hai:", execPath);
      return execPath;
    }
  } catch {}

  // 4. Common fixed paths
  const commonPaths = [
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
    "/usr/bin/google-chrome",
    "/usr/bin/google-chrome-stable",
    "/snap/bin/chromium",
  ];
  for (const p of commonPaths) {
    if (existsSync(p)) return p;
  }

  console.warn("[WA] ⚠️ Chromium nahi mila — puppeteer default use karega");
  return null; // puppeteer khud handle karega
}

const accounts = [
  { client: null, status: "disconnected", phoneNumber: "" },
  { client: null, status: "disconnected", phoneNumber: "" },
];

let onPairingCode = () => {};
let onReady = () => {};
let onDisconnected = () => {};

function setCallbacks(opts) {
  if (opts.onPairingCode) onPairingCode = opts.onPairingCode;
  if (opts.onReady) onReady = opts.onReady;
  if (opts.onDisconnected) onDisconnected = opts.onDisconnected;
}

function getStatus(index) { return accounts[index].status; }
function getPhone(index) { return accounts[index].phoneNumber; }

async function connectAccount(index, phoneNumber) {
  const existing = accounts[index].client;
  if (existing) { try { await existing.destroy(); } catch {} }

  accounts[index].status = "connecting";
  accounts[index].phoneNumber = phoneNumber;

  const chromiumPath = findChromium();

  const puppeteerConfig = {
    headless: true,
    args: [
      "--no-sandbox",
      "--disable-setuid-sandbox",
      "--disable-dev-shm-usage",
      "--disable-accelerated-2d-canvas",
      "--no-first-run",
      "--no-zygote",
      "--single-process",
      "--disable-gpu",
      "--disable-extensions",
      "--disable-software-rasterizer",
      "--disable-features=VizDisplayCompositor",
    ],
  };

  // Sirf tab set karo jab mil gaya ho
  if (chromiumPath) {
    puppeteerConfig.executablePath = chromiumPath;
  }

  const client = new Client({
    authStrategy: new LocalAuth({ clientId: `wa-account-${index + 1}` }),
    puppeteer: puppeteerConfig,
  });

  accounts[index].client = client;

  client.on("qr", async () => {
    try {
      const code = await client.requestPairingCode(phoneNumber);
      onPairingCode(index, code);
    } catch (err) {
      console.error(`[WA${index + 1}] Pairing code error:`, err.message);
    }
  });

  client.on("ready", () => {
    accounts[index].status = "connected";
    console.log(`[WA${index + 1}] ✅ Connected — ${phoneNumber}`);
    onReady(index);
  });

  client.on("disconnected", (reason) => {
    accounts[index].status = "disconnected";
    console.log(`[WA${index + 1}] Disconnected:`, reason);
    onDisconnected(index);
  });

  client.on("auth_failure", (msg) => {
    accounts[index].status = "disconnected";
    console.error(`[WA${index + 1}] Auth failure:`, msg);
    onDisconnected(index);
  });

  await client.initialize();
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
  try {
    const chats = await acc.client.getChats();
    return chats.filter((c) => c.isGroup).map((c) => ({ id: c.id._serialized, name: c.name }));
  } catch (err) {
    console.error(`[WA${index + 1}] getChats error:`, err.message);
    return [];
  }
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

module.exports = {
  setCallbacks, getStatus, getPhone,
  connectAccount, disconnectAccount,
  getAllGroups, sendMessageToGroup,
};
