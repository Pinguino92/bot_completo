# Multisport Bot

## Setup su GitHub + Render
1. Crea una repo su GitHub con questi file.
2. Vai su Render → New + → Web Service.
3. Collega la repo.
4. Aggiungi Environment Variables:
   - `ODDS_API_KEY` = la tua chiave Odds API
   - `TELEGRAM_TOKEN` = il token del bot Telegram
   - `TELEGRAM_CHAT_ID` = il tuo chat ID
5. Deploy. Il bot parte in automatico.

⏰ Scheduler: ogni 30 minuti dalle 08:00 alle 23:00 invia pronostici su Telegram.
