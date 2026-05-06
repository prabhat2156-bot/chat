const { Client, LocalAuth } = require("whatsapp-web.js");
const { execSync } = require("child_process");

function findChromium() {
  // Render / cloud environments mein CHROMIUM_PATH set karein
  if (process.env.CHROMIUM_PATH) return process.env.CHROMIUM_PATH;

  // Puppeteer ka bundled chromium check karo (npm install puppeteer ke baad)
  try {
    const puppeteer = require("puppeteer");
    const execPath = puppeteer.executablePath();
    if (execPath) return execPath;
  } catch {}

  // System chromium dhundo
  try {
    return execSync(
      "which chromium || which chromium-browser || which google-chrome-stable || which google-chrome",
      { encoding: "utf8" }
    ).trim();
  } catch {}

  // Render default path
  return "/usr/bin/google-chrome-stable";
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

  const client = new Client({
    authStrategy: new LocalAuth({ clientId: `wa-account-${index + 1}` }),
    puppeteer: {
      headless: true,
      executablePath: findChromium(),
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
        "--disable-background-networking",
        "--disable-background-timer-throttling",
        "--disable-backgrounding-occluded-windows",
        "--disable-breakpad",
        "--disable-client-side-phishing-detection",
        "--disable-component-extensions-with-background-pages",
        "--disable-default-apps",
        "--disable-features=TranslateUI",
        "--disable-hang-monitor",
        "--disable-ipc-flooding-protection",
        "--disable-popup-blocking",
        "--disable-prompt-on-repost",
        "--disable-renderer-backgrounding",
        "--disable-sync",
        "--force-color-profile=srgb",
        "--metrics-recording-only",
        "--safebrowsing-disable-auto-update",
      ],
    },
  });

  accounts[index].client = client;

  // ── FIX: QR event par pairing code request karo, error bhi propagate karo ──
  client.on("qr", async () => {
    try {
      console.log(`[WA${index + 1}] QR mila — pairing code request kar raha hai...`);

      // 30 second timeout for pairing code request
      const code = await Promise.race([
        client.requestPairingCode(phoneNumber),
        new Promise((_, reject) =>
          setTimeout(() => reject(new Error("Pairing code timeout (30s)")), 30000)
        ),
      ]);

      console.log(`[WA${index + 1}] Pairing code mila!`);
      onPairingCode(index, code, null); // success
    } catch (err) {
      console.error(`[WA${index + 1}] Pairing code error:`, err.message);
      // ── YAHAN PEHLE BUG THA: error propagate nahi ho raha tha ──
      onPairingCode(index, null, err); // error user tak pahuncho
    }
  });

  client.on("ready", () => {
    accounts[index].status = "connected";
    console.log(`[WA${index + 1}] Connected!`);
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

module.exports = { setCallbacks, getStatus, getPhone, connectAccount, disconnectAccount, getAllGroups, sendMessageToGroup };
