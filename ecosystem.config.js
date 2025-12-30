module.exports = {
  apps: [
    {
      name: "hedgegram_main",
      script: "main.py",
      interpreter: "python3",
      env: {
        ENV_FILE: ".env"
      }
    },
    {
      name: "hedgegram_telegram",
      script: "telegram_bot.py",
      interpreter: "python3",
      env: {
        ENV_FILE: ".env"
      }
    }
  ]
}
