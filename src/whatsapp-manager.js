const { Client, LocalAuth } = require("whatsapp-web.js");

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

function getStatus(index) {
  return accounts[index].status;
}

function getPhone(index) {
  return accounts[index].phoneNumber;
}

async function connectAccount(index, phoneNumber) {
  const existing = accounts[index].client;

  if (existing) {
    try {
      await existing.destroy();
    } catch {}
  }

  accounts[index].status = "connecting";
  accounts[index].phoneNumber = phoneNumber;

  const client = new Client({
    authStrategy: new LocalAuth({
      clientId: `wa-account-${index + 1}`,
    }),

    puppeteer: {
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
      ],
    },
  });

  accounts[index].client = client;

  // Pairing Code Login
  client.on("qr", async () => {
    try {
      console.log(`[WA${index + 1}] Generating pairing code...`);

      const pairingCode = await client.requestPairingCode(
        phoneNumber
      );

      console.log(
        `[WA${index + 1}] Pairing Code: ${pairingCode}`
      );

      onPairingCode(index, pairingCode);
    } catch (err) {
      console.error(
        `[WA${index + 1}] Pairing Code Error:`,
        err.message
      );
    }
  });

  client.on("ready", () => {
    accounts[index].status = "connected";

    console.log(
      `[WA${index + 1}] WhatsApp Connected Successfully`
    );

    onReady(index);
  });

  client.on("disconnected", (reason) => {
    accounts[index].status = "disconnected";

    console.log(
      `[WA${index + 1}] Disconnected:`,
      reason
    );

    onDisconnected(index);
  });

  client.on("auth_failure", (msg) => {
    accounts[index].status = "disconnected";

    console.log(
      `[WA${index + 1}] Auth Failure:`,
      msg
    );

    onDisconnected(index);
  });

  await client.initialize();
}

async function disconnectAccount(index) {
  const acc = accounts[index];

  if (acc.client) {
    try {
      await acc.client.destroy();
    } catch {}

    acc.client = null;
  }

  acc.status = "disconnected";
  acc.phoneNumber = "";
}

async function getAllGroups(index) {
  const acc = accounts[index];

  if (!acc.client || acc.status !== "connected") {
    return [];
  }

  const chats = await acc.client.getChats();

  return chats
    .filter((c) => c.isGroup)
    .map((c) => ({
      id: c.id._serialized,
      name: c.name,
    }));
}

async function sendMessageToGroup(index, groupId, message) {
  const acc = accounts[index];

  if (!acc.client || acc.status !== "connected") {
    return false;
  }

  try {
    const chat = await acc.client.getChatById(groupId);

    await chat.sendMessage(message);

    return true;
  } catch (err) {
    console.error(
      `[WA${index + 1}] Send Error:`,
      err.message
    );

    return false;
  }
}

module.exports = {
  setCallbacks,
  getStatus,
  getPhone,
  connectAccount,
  disconnectAccount,
  getAllGroups,
  sendMessageToGroup,
};
