const { readFileSync, existsSync } = require("fs");
const { join } = require("path");

function readScript(num) {
  const filePath = join(__dirname, "..", "data", `script${num}.txt`);
  if (!existsSync(filePath)) return [];
  const content = readFileSync(filePath, "utf8");
  return content
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line.length > 0);
}

function randomMessage(messages) {
  if (messages.length === 0) return "";
  return messages[Math.floor(Math.random() * messages.length)];
}

module.exports = { readScript, randomMessage };
