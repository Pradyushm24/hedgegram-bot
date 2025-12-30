📄 VPS_RESTORE.md (FULL CONTENT)
Copy code
Md
# 🛠️ Hedgegram Bot – VPS Restore & Daily Ops Guide

Ye document future ke liye hai.
Agar VPS suspend ho jaaye, IP change ho jaaye, ya naya VPS lena pade,
to **sirf is file ko follow karke 30–45 min me bot live ho sakta hai**.

---

## 🔐 1. VPS BASIC SETUP (NEW VPS)

```bash
apt update && apt upgrade -y
apt install -y git python3 python3-venv python3-pip nginx curl ufw
Enable firewall:
Copy code
Bash
ufw allow OpenSSH
ufw allow 80
ufw allow 443
ufw enable
📦 2. PROJECT CLONE
Copy code
Bash
cd ~
git clone https://github.com/<YOUR_GITHUB_USERNAME>/hedgegram-bot.git hedgegram
cd hedgegram
🐍 3. PYTHON VENV SETUP
Copy code
Bash
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
pip install pyotp pm2
🔑 4. .env FILE (MANUAL – NEVER PUSH TO GITHUB)
Copy code
Bash
nano .env
Example:
Copy code
Env
TELEGRAM_BOT_TOKEN=xxxxx
TELEGRAM_CHAT_ID=xxxxx

CONTROL_API_KEY=xxxxxxxx
CONTROL_API_BASE=http://127.0.0.1:8000/control

FLATTRADE_CLIENT_ID=FTXXXXXX
FLATTRADE_API_SECRET=xxxxxxxx
FLATTRADE_TOTP_SECRET=xxxxxxxx

FLATTRADE_LOGIN_URL=https://authapi.flattrade.in/ftauth
Permissions:
Copy code
Bash
chmod 600 .env
🌐 5. DOMAIN + NGINX (CALLBACK REQUIRED FOR LIVE)
Domain example:
Copy code

bot.hedgegram.sbs
Nginx file:
Copy code
Bash
nano /etc/nginx/sites-available/bot.hedgegram.sbs
Paste:
Copy code
Nginx
server {
    listen 80;
    server_name bot.hedgegram.sbs;
    location / {
        return 301 https://$host$request_uri;
    }
}

server {
    listen 443 ssl http2;
    server_name bot.hedgegram.sbs;

    ssl_certificate /etc/letsencrypt/live/bot.hedgegram.sbs/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/bot.hedgegram.sbs/privkey.pem;

    location /callback {
        proxy_pass http://127.0.0.1:9000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
Enable & reload:
Copy code
Bash
ln -s /etc/nginx/sites-available/bot.hedgegram.sbs /etc/nginx/sites-enabled/
nginx -t
systemctl reload nginx
🔐 6. SSL CERTIFICATE
Copy code
Bash
apt install certbot python3-certbot-nginx -y
certbot --nginx -d bot.hedgegram.sbs
Verify:
Copy code
Bash
curl -I https://bot.hedgegram.sbs/callback
Expected: 405 Method Not Allowed (THIS IS OK)
⚙️ 7. PM2 SERVICES
Copy code
Bash
pm2 start main.py --name hedgegram_main --interpreter ./venv/bin/python
pm2 start telegram_bot.py --name hedgegram_telegram --interpreter ./venv/bin/python
pm2 start callback.py --name hedgegram_callback --interpreter ./venv/bin/python

pm2 save
pm2 startup
Check:
Copy code
Bash
pm2 ls
🤖 8. TELEGRAM BOT COMMANDS (BotFather)
Copy code

start - start strategy
stop - stop strategy
status - bot status
positions - current positions
paper - switch to paper mode
live - switch to live mode
help - help menu
🔁 9. DAILY MORNING ROUTINE (LIVE TRADING)
1️⃣ Browser me Flattrade login
2️⃣ Access token generate
3️⃣ Paste token:
Copy code
Bash
nano live_auth.json
Example:
Copy code
Json
{
  "jwtToken": "PASTE_TOKEN_HERE",
  "clientcode": "FTXXXXXX"
}
4️⃣ Telegram:
Copy code

/live
/start
🧪 10. PAPER MODE (NO FUNDS REQUIRED)
Copy code
Text
/paper
/start
/status
✔ Paper mode real market LTP ke saath PnL show karta hai
✔ Backtest / logic test ke liye perfect
⚠️ 11. COMMON ISSUES
❌ "Live auth missing"
✔ live_auth.json missing / expired
❌ 502 Bad Gateway
✔ Callback service down ✔ Nginx proxy wrong port
❌ Telegram bot not responding
✔ pm2 logs check:
Copy code
Bash
pm2 logs hedgegram_telegram
💾 12. SAFE FILES TO PUSH GITHUB
✅ main.py
✅ telegram_bot.py
✅ callback.py
✅ VPS_RESTORE.md
✅ config.json
❌ .env
❌ live_auth.json
❌ logs / venv
