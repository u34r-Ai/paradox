import os
import logging
from typing import Dict, List, Any

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("trading_bot.log")
    ]
)

logger = logging.getLogger(__name__)

# Telegram Configuration
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Exchange API Configuration
EXCHANGE_NAME = os.getenv("EXCHANGE_NAME", "kucoin")
API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")

# Proxy Configuration - for connecting from regions with restrictions
HTTP_PROXY = os.getenv("HTTP_PROXY")
HTTPS_PROXY = os.getenv("HTTPS_PROXY")

# Trading Parameters
SYMBOL = os.getenv("TRADING_SYMBOL", "BTC/USDT")
QUOTE_CURRENCY = SYMBOL.split('/')[1]
BASE_CURRENCY = SYMBOL.split('/')[0]
TIMEFRAME = os.getenv("TIMEFRAME", "5m")
POSITION_SIZE_PERCENTAGE = float(os.getenv("POSITION_SIZE_PERCENTAGE", "25"))  # % of available balance
MAX_LEVERAGE = int(os.getenv("MAX_LEVERAGE", "20"))
MIN_LEVERAGE = int(os.getenv("MIN_LEVERAGE", "5"))

# Stop Loss and Take Profit Settings
STOP_LOSS_PERCENTAGE = float(os.getenv("STOP_LOSS_PERCENTAGE", "3"))  # % from entry price
MIN_TAKE_PROFIT_PERCENTAGE = float(os.getenv("MIN_TAKE_PROFIT_PERCENTAGE", "6"))  # % from entry price
MAX_TAKE_PROFIT_PERCENTAGE = float(os.getenv("MAX_TAKE_PROFIT_PERCENTAGE", "8"))  # % from entry price

# Trading Strategy Parameters
RSI_PERIOD = int(os.getenv("RSI_PERIOD", "14"))
RSI_OVERBOUGHT = float(os.getenv("RSI_OVERBOUGHT", "70"))
RSI_OVERSOLD = float(os.getenv("RSI_OVERSOLD", "30"))
EMA_SHORT = int(os.getenv("EMA_SHORT", "9"))
EMA_MEDIUM = int(os.getenv("EMA_MEDIUM", "21"))
EMA_LONG = int(os.getenv("EMA_LONG", "50"))
VOLUME_THRESHOLD = float(os.getenv("VOLUME_THRESHOLD", "1.5"))  # multiple of average volume

# Risk Management
MAX_DRAWDOWN_PERCENTAGE = float(os.getenv("MAX_DRAWDOWN_PERCENTAGE", "15"))  # % of total capital
MAX_DAILY_TRADES = int(os.getenv("MAX_DAILY_TRADES", "5"))
MAX_OPEN_POSITIONS = int(os.getenv("MAX_OPEN_POSITIONS", "1"))

# Application Settings
TRADING_ACTIVE = os.getenv("TRADING_ACTIVE", "true").lower() == "true"
NOTIFICATION_ACTIVE = os.getenv("NOTIFICATION_ACTIVE", "true").lower() == "true"
LOOP_INTERVAL = int(os.getenv("LOOP_INTERVAL", "30"))  # seconds

def get_trading_params() -> Dict[str, Any]:
    """Return all trading parameters as a dictionary."""
    return {
        "exchange": EXCHANGE_NAME,
        "symbol": SYMBOL,
        "timeframe": TIMEFRAME,
        "position_size_percentage": POSITION_SIZE_PERCENTAGE,
        "max_leverage": MAX_LEVERAGE,
        "min_leverage": MIN_LEVERAGE,
        "stop_loss_percentage": STOP_LOSS_PERCENTAGE,
        "min_take_profit_percentage": MIN_TAKE_PROFIT_PERCENTAGE, 
        "max_take_profit_percentage": MAX_TAKE_PROFIT_PERCENTAGE,
        "rsi_period": RSI_PERIOD,
        "rsi_overbought": RSI_OVERBOUGHT,
        "rsi_oversold": RSI_OVERSOLD,
        "ema_short": EMA_SHORT,
        "ema_medium": EMA_MEDIUM,
        "ema_long": EMA_LONG,
        "volume_threshold": VOLUME_THRESHOLD,
        "max_drawdown": MAX_DRAWDOWN_PERCENTAGE,
        "max_daily_trades": MAX_DAILY_TRADES,
        "max_open_positions": MAX_OPEN_POSITIONS
    }

def validate_config() -> bool:
    """Validate that all required configuration parameters are set."""
    required_vars = [
        "TELEGRAM_TOKEN", 
        "TELEGRAM_CHAT_ID", 
        "API_KEY", 
        "API_SECRET"
    ]
    
    missing_vars = [var for var in required_vars if not globals().get(var)]
    
    if missing_vars:
        logger.error(f"Missing required environment variables: {', '.join(missing_vars)}")
        return False
        
    logger.info("Configuration validated successfully")
    return True
