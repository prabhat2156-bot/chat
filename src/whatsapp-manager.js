const { Client, LocalAuth } = require("whatsapp-web.js");
const { execSync } = require("child_process");
const fs = require("fs");
const path = require("path");
const os = require("os");

function findChromium() {
  // 1. Manual env variable (sabse zyada priority)
  if (process.env.CHROMIUM_PATH && fs.existsSync(process.env.CHROMIUM_PATH)) {
    console.log("[Chrome] CHROMIUM_PATH use kar raha hai:", process.env.CHROMIUM_PATH);
    return process.env.CHROMIUM_PATH;
  }

  // 2. Puppeteer ka executablePath — lekin pehle check karo ki file exist karti hai
  try {
    const puppeteer = require("puppeteer");
    const execPath = puppeteer.executablePath();
    if (execPath && fs.existsSync(execPath)) {
      console.log("[Chrome] Puppeteer executablePath mila:", execPath);
      return execPath;
    }
    console.log("[Chrome] puppeteer.executablePath() ne diya:", execPath, "— lekin file nahi mili");
  } catch (e) {
    console.log("[Chrome] puppeteer require fail:", e.message);
  }

  // 3. Puppeteer cache directory manually dhundo
  const cacheDirs = [
    process.env.PUPPETEER_CACHE_DIR,
    "/opt/render/project/src/.cache/puppeteer",
    path.join(os.homedir(), ".cache", "puppeteer"),
    path.join(process.cwd(), ".cache", "puppeteer"),
    "/root/.cache/puppeteer",
  ].filter(Boolean);

  for (const cacheDir of cacheDirs) {
    try {
      if (!fs.existsSync(cacheDir)) continue;
      const chromeDir = path.join(cacheDir, "chrome");
      if (!fs.existsSync(chromeDir)) continue;

      // linux-xxx/chrome-linux/chrome format mein dhundo
      for (const platform of fs.readdirSync(chromeDir)) {
        const platformDir = path.join(chromeDir, platform);
        if (!fs.statSync(platformDir).isDirectory()) continue;
        for (const version of fs.readdirSync(platformDir)) {
          const candidates = [
            path.join(platformDir, version, "chrome"),
            path.join(platformDir, version, "chrome-linux", "chrome"),
            path.join(platformDir, version, "chrome-linux64", "chrome"),
          ];
          for (const c of candidates) {
            if (fs.existsSync(c)) {
              console.log("[Chrome] Cache mein mila:", c);
              return c;
            }
          }
        }
      }
    } catch {}
  }

  // 4. System chromium dhundo
  try {
    const found = execSync(
      "which google-chrome-stable || which google-chrome || which chromium-browser || which chromium 2>/dev/null",
      { encoding: "utf8" }
    ).trim();
    if (found && fs.existsSync(found)) {
      console.log("[Chrome] System chromium mila:", found);
      return found;
    }
  } catch {}

  // 5. Kuch nahi mila — clear error
  throw new Error(
    "Chrome nahi mila!\n\n" +
    "Render Dashboard mein jaao aur:\n" +
    "Settings → Build Command mein yeh set karein:\n" +
    "npm install && npx puppeteer browsers install chrome\n\n" +
    "Ya environment variable set karein:\n" +
    "PUPPETEER_CACHE_DIR = /opt/render/project/src/.cache/puppeteer"
  );
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

  let chromePath;
  try {
    chromePath = findChromium();
  } catch (err) {
    accounts[index].status = "disconnected";
    throw err;
  }

  const client = new Client({
    authStrategy: new LocalAuth({ clientId: `wa-account-${index + 1}` }),
    puppeteer: {
      headless: true,
      executablePath: chromePath,
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

  client.on("qr", async () => {
    try {
      console.log(`[WA${index + 1}] QR mila — pairing code request kar raha hai...`);
      const code = await Promise.race([
        client.requestPairingCode(phoneNumber),
        new Promise((_, reject) =>
          setTimeout(() => reject(new Error("Pairing code timeout (30s)")), 30000)
        ),
      ]);
      console.log(`[WA${index + 1}] Pairing code mila!`);
      onPairingCode(index, code, null);
    } catch (err) {
      console.error(`[WA${index + 1}] Pairing code error:`, err.message);
      onPairingCode(index, null, err);
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
