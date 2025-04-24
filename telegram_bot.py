import logging
import os
import threading
import time
import requests
from datetime import datetime
from typing import Dict, Any, List, Optional

import config
from utils import TradingState, format_price

logger = logging.getLogger(__name__)

class TelegramBot:
    def __init__(self, trading_state: TradingState):
        """Initialize Telegram bot with trading state reference."""
        self.token = config.TELEGRAM_TOKEN
        self.chat_id = config.TELEGRAM_CHAT_ID
        self.state = trading_state
        self.api_url = f"https://api.telegram.org/bot{self.token}"
        self.initialized = False
        self.message_queue = []
        self.message_lock = threading.Lock()
        self.bot_thread = None
        self.running = False
        
        # Initialize bot if token is available
        if self.token and self.chat_id:
            self.initialized = True
            logger.info("Telegram bot initialized")
        else:
            logger.error("Telegram bot token or chat ID not provided")
    
    def start(self):
        """Start the bot in a separate thread."""
        if not self.initialized:
            logger.error("Cannot start Telegram bot: not initialized")
            return False
            
        def run_bot():
            """Run the bot in the background thread."""
            try:
                self.running = True
                logger.info("Starting Telegram bot...")
                self.send_message("🤖 Trading Bot Started\n\nUse /help to see available commands")
                
                # Start polling for updates
                offset = 0
                while self.running:
                    try:
                        updates = self._get_updates(offset)
                        if updates.get('ok') and updates.get('result'):
                            for update in updates['result']:
                                offset = update['update_id'] + 1
                                self._process_update(update)
                    except Exception as e:
                        logger.error(f"Error in Telegram update loop: {e}")
                    
                    time.sleep(1)
            except Exception as e:
                logger.error(f"Error in Telegram bot thread: {e}")
                self.running = False
            
        self.bot_thread = threading.Thread(target=run_bot, daemon=True)
        self.bot_thread.start()
        logger.info("Telegram bot thread started")
        return True
        
    def stop(self):
        """Stop the Telegram bot."""
        self.running = False
        if self.bot_thread and self.bot_thread.is_alive():
            self.bot_thread.join(timeout=2)
        logger.info("Telegram bot stopped")
            
    def is_running(self) -> bool:
        """Check if the bot is running."""
        thread_alive = False
        if self.bot_thread is not None:
            thread_alive = self.bot_thread.is_alive()
        return bool(self.initialized and self.running and thread_alive)
    
    def _get_updates(self, offset=0, timeout=30):
        """Get updates from Telegram API."""
        params = {
            'offset': offset,
            'timeout': timeout
        }
        
        try:
            # Initialize proxy settings
            proxies = None
            if config.HTTP_PROXY or config.HTTPS_PROXY:
                proxies = {
                    'http': config.HTTP_PROXY,
                    'https': config.HTTPS_PROXY
                }
                
            # First attempt with proxy if available
            response = requests.get(f"{self.api_url}/getUpdates", 
                                   params=params, 
                                   proxies=proxies, 
                                   timeout=10)
            if response.status_code == 200:
                return response.json()
            else:
                logger.warning(f"Failed to get updates: {response.status_code} - {response.text}")
                return {}
                
        except Exception as e:
            logger.warning(f"Error getting updates with proxy: {e}")
            
            # Try without proxy as fallback
            if proxies:
                try:
                    logger.info("Attempting to get updates without proxy")
                    response = requests.get(f"{self.api_url}/getUpdates", 
                                           params=params, 
                                           proxies=None, 
                                           timeout=10)
                    if response.status_code == 200:
                        return response.json()
                    else:
                        logger.warning(f"Failed to get updates without proxy: {response.status_code} - {response.text}")
                except Exception as e2:
                    logger.error(f"Error getting updates without proxy: {e2}")
            
            return {}
        
    def _process_update(self, update):
        """Process an update from Telegram."""
        try:
            # Check if this is a message
            if 'message' in update:
                message = update['message']
                
                # Check if this is a command
                if 'text' in message:
                    text = message['text']
                    
                    if text.startswith('/'):
                        command = text.split()[0].lower()
                        
                        if command == '/start':
                            self._handle_start_command(message)
                        elif command == '/status':
                            self._handle_status_command(message)
                        elif command == '/pnl':
                            self._handle_pnl_command(message)
                        elif command == '/balance':
                            self._handle_balance_command(message)
                        elif command == '/trades':
                            self._handle_trades_command(message)
                        elif command == '/stop':
                            self._handle_stop_command(message)
                        elif command == '/help':
                            self._handle_help_command(message)
                        else:
                            self._send_reply(message, "I don't understand that command. Use /help to see available commands.")
                    else:
                        self._send_reply(message, "I only respond to commands. Use /help to see available commands.")
        except Exception as e:
            logger.error(f"Error processing update: {e}")
            
    def _send_reply(self, message, text):
        """Send a reply to a message."""
        chat_id = message['chat']['id']
        self._send_message(chat_id, text)
        
    def _send_message(self, chat_id, text):
        """Send a message to a specific chat."""
        params = {
            'chat_id': chat_id,
            'text': text,
            'parse_mode': 'HTML'
        }
        try:
            # Try to send without proxy first
            proxies = None
            
            # Add proxy settings if available in config
            if config.HTTP_PROXY or config.HTTPS_PROXY:
                proxies = {
                    'http': config.HTTP_PROXY,
                    'https': config.HTTPS_PROXY
                }
                
            # Send with 10 second timeout
            response = requests.post(
                f"{self.api_url}/sendMessage", 
                params=params, 
                proxies=proxies,
                timeout=10
            )
            
            if not response.json().get('ok'):
                logger.error(f"Failed to send message: {response.text}")
                return False
                
            logger.info(f"Message sent to Telegram: {text[:50]}...")
            return True
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            
            # If proxy failed, try without proxy as a fallback
            if proxies:
                try:
                    logger.info("Attempting to send message without proxy")
                    response = requests.post(
                        f"{self.api_url}/sendMessage", 
                        params=params, 
                        proxies=None,
                        timeout=10
                    )
                    
                    if not response.json().get('ok'):
                        logger.error(f"Failed to send message (fallback): {response.text}")
                        return False
                        
                    logger.info(f"Message sent to Telegram without proxy: {text[:50]}...")
                    return True
                except Exception as e2:
                    logger.error(f"Error sending message without proxy: {e2}")
                    return False
            return False
    
    def _handle_start_command(self, message):
        """Handle /start command."""
        self._send_reply(message, 
            "🤖 Welcome to the Trading Bot!\n\n"
            "I'll keep you updated on trades and account status.\n"
            "Use /help to see available commands."
        )
        
    def _handle_status_command(self, message):
        """Handle /status command."""
        status = self.state.get_status()
        
        if status['active_position']:
            position_info = (
                f"Position: {status['position_side']} {status['position_size']:.4f} @ {status['position_entry_price']:.2f}\n"
                f"Leverage: {status['position_leverage']}x\n"
                f"Take Profit: {status['take_profit_price']:.2f}\n"
                f"Stop Loss: {status['stop_loss_price']:.2f}"
            )
        else:
            position_info = "No active position"
            
        text = (
            f"📊 Current Status\n\n"
            f"Symbol: {config.SYMBOL}\n"
            f"Balance: {status['current_balance']:.2f} {config.QUOTE_CURRENCY}\n"
            f"Total PnL: {status['total_pnl']:.2f} {config.QUOTE_CURRENCY}\n"
            f"Daily Trades: {status['daily_trades']}/{config.MAX_DAILY_TRADES}\n"
            f"AI Confidence: {status['ai_confidence']:.2f}\n"
            f"Market Volatility: {status['volatility']:.2f}%\n\n"
            f"{position_info}"
        )
        
        self._send_reply(message, text)
        
    def _handle_pnl_command(self, message):
        """Handle /pnl command."""
        if self.state.initial_balance == 0:
            self._send_reply(message, "PnL data not available yet. Waiting for initial balance.")
            return
            
        pnl = self.state.total_pnl
        pnl_percentage = (pnl / self.state.initial_balance) * 100 if self.state.initial_balance > 0 else 0
        
        text = (
            f"💰 Profit & Loss\n\n"
            f"Initial Balance: {self.state.initial_balance:.2f} {config.QUOTE_CURRENCY}\n"
            f"Current Balance: {self.state.current_balance:.2f} {config.QUOTE_CURRENCY}\n"
            f"Total PnL: {pnl:.2f} {config.QUOTE_CURRENCY} ({pnl_percentage:.2f}%)"
        )
        
        self._send_reply(message, text)
        
    def _handle_balance_command(self, message):
        """Handle /balance command."""
        text = (
            f"💵 Account Balance\n\n"
            f"Current Balance: {self.state.current_balance:.2f} {config.QUOTE_CURRENCY}"
        )
        
        self._send_reply(message, text)
        
    def _handle_trades_command(self, message):
        """Handle /trades command."""
        if not self.state.trades_history:
            self._send_reply(message, "No trades executed yet.")
            return
            
        # Get recent trades (last 5)
        recent_trades = self.state.trades_history[-5:]
        
        text = "🔄 Recent Trades\n\n"
        
        for i, trade in enumerate(recent_trades, 1):
            trade_time = trade['time'].strftime('%Y-%m-%d %H:%M:%S')
            pnl = trade['pnl']
            side = trade['side']
            entry = trade['entry_price']
            exit_price = trade['exit_price']
            leverage = trade['leverage']
            
            text += (
                f"{i}. {trade_time}\n"
                f"   {side.upper()} @ {entry:.2f} → {exit_price:.2f}\n"
                f"   Leverage: {leverage}x\n"
                f"   PnL: {pnl:.2f} {config.QUOTE_CURRENCY}\n\n"
            )
            
        text += f"Total PnL: {self.state.total_pnl:.2f} {config.QUOTE_CURRENCY}"
        
        self._send_reply(message, text)
        
    def _handle_stop_command(self, message):
        """Handle /stop command."""
        self._send_reply(message, 
            "⚠️ To stop the trading bot, you need to stop the application from the host system.\n\n"
            "This bot will continue running until the host application is stopped."
        )
        
    def _handle_help_command(self, message):
        """Handle /help command."""
        help_text = (
            "📋 Available Commands\n\n"
            "/start - Welcome message\n"
            "/status - Current trading status\n"
            "/pnl - Show profit/loss information\n"
            "/balance - Show account balance\n"
            "/trades - List recent trades\n"
            "/help - Show this help message"
        )
        
        self._send_reply(message, help_text)
        
    def send_message(self, message: str) -> bool:
        """
        Send a message to the predefined chat.
        This method is thread-safe and can be called from any thread.
        """
        if not self.initialized or not self.token or not self.chat_id:
            logger.error("Cannot send message: Telegram bot not properly initialized")
            return False
            
        try:
            self._send_message(self.chat_id, message)
            logger.info(f"Message sent to Telegram: {message[:50]}...")
            return True
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")
            return False
            
    def notify_trade_opened(self, symbol: str, side: str, size: float, price: float, leverage: int = 1) -> bool:
        """Notify about a new trade that was opened."""
        message = (
            f"🟢 Trade Opened\n\n"
            f"Symbol: {symbol}\n"
            f"Side: {side.upper()}\n"
            f"Size: {size:.4f}\n"
            f"Price: {price:.2f}\n"
            f"Leverage: {leverage}x\n"
            f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        
        return self.send_message(message)
        
    def notify_trade_closed(self, symbol: str, side: str, entry_price: float, exit_price: float, 
                           pnl: float, roi_percentage: float) -> bool:
        """Notify about a trade that was closed."""
        pnl_emoji = "🟢" if pnl >= 0 else "🔴"
        
        message = (
            f"{pnl_emoji} Trade Closed\n\n"
            f"Symbol: {symbol}\n"
            f"Side: {side.upper()}\n"
            f"Entry: {entry_price:.2f}\n"
            f"Exit: {exit_price:.2f}\n"
            f"PnL: {pnl:.4f} {config.QUOTE_CURRENCY}\n"
            f"ROI: {roi_percentage:.2f}%\n"
            f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        
        return self.send_message(message)
        
    def notify_error(self, error_message: str) -> bool:
        """Notify about an error."""
        message = f"⚠️ Error\n\n{error_message}\n\nTime: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        return self.send_message(message)
        
    def send_system_status(self) -> bool:
        """Send system status message."""
        message = f"✅ All systems checked. Trading live. You may now close the Replit tab."
        return self.send_message(message)