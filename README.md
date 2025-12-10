Hedgegram Automated Options Trading Bot

A fully automated trading system for NIFTY / FINNIFTY option strategies, featuring:

✔ Telegram-based control (start, stop, status, P&L, positions, panic exit)

✔ Paper mode & Live mode

✔ Flattrade API integration (token via TOTP OR via Telegram /settoken)

✔ Daily token auto-clear

✔ PnL per-leg calculation

✔ Re-entry logic, trailing SL, expiry exit

✔ Runs persistently via tmux / systemd / Docker



---

📁 Repository Structure

hedgegram-bot/
├── README.md
├── requirements.txt
├── config.json
├── main.py                 # API + strategy engine
├── telegram_bot.py         # Admin Telegram bot
├── cancel_all.py
├── cancel_all.sh
├── start.sh
├── monitor.sh
├── migrate_old.sh
├── examples/
│   ├── .env.example
│   └── flattrade_code.example.json
├── scripts/
│   └── helpers.sh
├── docker-compose.yml      # optional
├── docs/
│   └── architecture.md
└── .gitignore
