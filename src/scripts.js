const { readFileSync, existsSync } = require("fs");
const { join } = require("path");

function readScript(num) {
  const filePath = join(__dirname, "..", "data", `script${num}.txt`);
  if (!existsSync(filePath)) return [];
  return readFileSync(filePath, "utf8")
    .split("\n")
    .map((l) => l.trim())
    .filter((l) => l.length > 0);
}

function randomMessage(messages) {
  if (!messages.length) return "";
  return messages[Math.floor(Math.random() * messages.length)];
}

module.exports = { readScript, randomMessage };
