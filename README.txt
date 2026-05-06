╔══════════════════════════════════════════╗
║   WhatsApp Broadcast Bot v2.0           ║
║   Telegram Bot — Full Setup Guide       ║
╚══════════════════════════════════════════╝

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 FEATURES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ 2 WhatsApp accounts (phone number pairing)
✅ Saare groups ya selected groups mein broadcast
✅ Har group ko RANDOM message milega
✅ Script files se messages (edit karein kabhi bhi)
✅ Schedule: 1 din / 10 din / Nonstop
✅ Repeat interval: 30min / 1hr / 6hr / 24hr
✅ Live broadcast status (real-time counter)
✅ Manual stop button
✅ Message delay setting
✅ Express HTTP server (Render deploy ke liye)
✅ Self-ping har 2 min (Render sleep prevent)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 ★ RENDER.COM PE 24/7 DEPLOY KARNA ★
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

STEP 1 — Code GitHub pe upload karein
  a) GitHub.com pe new repository banao (public ya private)
  b) Yeh saara folder us repo mein upload karo

STEP 2 — Render pe service banao
  a) render.com pe jaao → Sign up / Login
  b) "New +" → "Web Service" click karein
  c) Apna GitHub repo connect karein
  d) Yeh settings bharo:
     ┌─────────────────────────────────────┐
     │ Name:         wa-broadcast-bot      │
     │ Runtime:      Node                  │
     │ Build Command: npm install          │
     │ Start Command: node index.js        │
     │ Instance Type: Free                 │
     └─────────────────────────────────────┘

STEP 3 — Environment Variables set karein
  Render dashboard → "Environment" tab mein:
  ┌───────────────────────┬─────────────────────────────┐
  │ KEY                   │ VALUE                       │
  ├───────────────────────┼─────────────────────────────┤
  │ TELEGRAM_BOT_TOKEN    │ aapka_bot_token_yahan       │
  │ RENDER_EXTERNAL_URL   │ https://wa-bot.onrender.com │
  └───────────────────────┴─────────────────────────────┘
  
  ⚠️ RENDER_EXTERNAL_URL = aapki render app ka URL
     (Deploy hone ke baad milega, phir add karein)

STEP 4 — Deploy karein
  "Create Web Service" dabao → Deploy automatically hoga
  
STEP 5 — Self-ping set karein
  Deploy hone ke baad aapki app ka URL milega:
  Example: https://wa-broadcast-bot-xxxx.onrender.com
  
  Yeh URL RENDER_EXTERNAL_URL mein paste karein
  → Bot khud apne aap ko har 2 minute mein ping karega
  → Service kabhi sleep nahi karegi! 🎉

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 RENDER HEALTH CHECK URLS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  https://aapki-app.onrender.com/        → Status page
  https://aapki-app.onrender.com/health  → JSON status

  /health response example:
  {
    "status": "ok",
    "uptime": "3600s",
    "wa1": "connected",
    "wa2": "disconnected"
  }

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 UBUNTU/VPS SERVER SETUP
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# 1. Node.js install karein
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt-get install -y nodejs

# 2. Chromium install karein
sudo apt update && sudo apt install chromium-browser -y

# 3. Dependencies install karein
cd wa-broadcast-bot
npm install

# 4. Bot start karein
TELEGRAM_BOT_TOKEN="token" node index.js

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 24/7 CHALANE KE LIYE (PM2)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

npm install -g pm2

TELEGRAM_BOT_TOKEN="token" \
RENDER_EXTERNAL_URL="https://aapki-app.onrender.com" \
pm2 start index.js --name wa-bot

pm2 save && pm2 startup
pm2 logs wa-bot

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 SCRIPT FILES (MESSAGES)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

data/script1.txt  →  WA Account 1 ke messages
data/script2.txt  →  WA Account 2 ke messages

Format: EK LINE = EK MESSAGE
Example:
---
Aaj ka offer sirf aaj ke liye!
Hamari nayi service launch ho gayi.
Limited time deal — jaldi faida uthao!
---
Bot restart ki zaroorat NAHI — live reload hota hai!

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 BOT USE KARNA (TELEGRAM)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. /start karein
2. WA Account connect karein → phone number dein
3. 30-60 sec mein pairing code aayega
4. WhatsApp → Settings → Linked Devices
   → Link with phone number → code enter karein
5. Schedule set karein (⏰ button)
6. Broadcast shuru karein (🚀 button)
7. Groups select karein → Confirm
8. Live status dekhein

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 FOLDER STRUCTURE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

wa-broadcast-bot/
├── index.js                 ← Main bot
├── package.json
├── README.txt
├── src/
│   ├── session.js
│   ├── scheduler.js
│   ├── scripts.js
│   └── whatsapp-manager.js
└── data/
    ├── script1.txt          ← WA1 ke messages
    └── script2.txt          ← WA2 ke messages

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 PROBLEM? SOLUTIONS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

❌ "Chrome not found":
   → CHROMIUM_PATH="/usr/bin/chromium" node index.js

❌ "Token not set":
   → TELEGRAM_BOT_TOKEN="token" node index.js

❌ Pairing code nahi aa raha:
   → 60 sec tak wait karein, phir dobara try karein

❌ Render pe "Build failed":
   → package.json mein "start": "node index.js" check karein

❌ Render pe bot band ho jaata hai:
   → RENDER_EXTERNAL_URL properly set hai? Check karein
   → /health URL browser mein kholo — response aana chahiye
