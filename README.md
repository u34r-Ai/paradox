# Cryptocurrency Trading Bot

This is a crypto trading bot with Telegram integration, AI-driven risk management, and automated execution.

## Features

- Real-time trading on cryptocurrency exchanges
- AI-based leverage control (5x-20x) based on market confidence
- Dynamic take-profit targeting (6-8%) based on market volatility
- 3% stop loss protection
- Telegram bot integration for notifications and commands
- Web interface for monitoring and control

## Trading Parameters

- Uses 25% of capital per trade
- Stop loss set at 3%
- Dynamic take-profit between 6-8% based on volatility
- AI-based leverage control (5x-20x) based on confidence score

## Deployment on Render

### Prerequisites

1. Create a [Render](https://render.com) account
2. Fork this repository to your GitHub account

### Deployment Steps

1. Log in to your Render account
2. Click on "New" and select "Web Service"
3. Connect your GitHub repository
4. Configure the service:
   - **Name**: crypto-trading-bot (or your preferred name)
   - **Environment**: Python
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn --bind 0.0.0.0:$PORT --reuse-port --reload main:app`

5. Add the following environment variables:
   - `API_KEY`: Your exchange API key
   - `API_SECRET`: Your exchange API secret
   - `TELEGRAM_TOKEN`: Your Telegram bot token
   - `TELEGRAM_CHAT_ID`: Your Telegram chat ID

6. Click "Create Web Service"

### Verification

After deployment:
1. Visit your Render service URL to verify the application is running
2. Check `/status` endpoint to confirm the service health
3. Start trading by accessing the `/api/start` endpoint or using Telegram commands

## Telegram Commands

- `/start` - Initialize the bot
- `/status` - Get current trading status
- `/pnl` - Check your profit and loss
- `/balance` - Check your current balance
- `/trades` - View recent trade history
- `/stop` - Stop the trading bot
- `/help` - Show available commands

## Security

- Never share your API keys or secrets
- Use environment variables for all sensitive information
- Ensure your exchange API keys have appropriate permissions (trading allowed, withdrawals disabled)

## Maintenance

The bot includes a health check endpoint at `/status` that Render will use to verify the service is running. The `/ping` endpoint is used by the scheduler to keep the service active.