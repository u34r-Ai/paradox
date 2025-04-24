import time
import logging
import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional, Any, Union
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Global state for the trading bot
class TradingState:
    def __init__(self):
        self.active_position = False
        self.position_entry_price = 0.0
        self.position_entry_time = None
        self.position_size = 0.0
        self.position_leverage = 0
        self.position_side = None  # 'long' or 'short'
        self.take_profit_price = 0.0
        self.stop_loss_price = 0.0
        self.daily_trades = 0
        self.daily_trades_reset_time = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        self.total_pnl = 0.0
        self.trades_history = []
        self.initial_balance = 0.0
        self.current_balance = 0.0
        self.ai_confidence = 0.0  # 0 to 1
        self.last_volatility = 0.0
        self.last_update_time = None
        self.last_check_time = datetime.now() # For health monitoring
        
    def reset_daily_trades(self):
        """Reset daily trades counter if a new day has started."""
        now = datetime.now()
        if now >= self.daily_trades_reset_time:
            self.daily_trades = 0
            self.daily_trades_reset_time = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
            logger.info("Daily trades counter reset")
    
    def update_pnl(self, pnl: float):
        """Update total PnL after a trade is closed."""
        self.total_pnl += pnl
        self.trades_history.append({
            'time': datetime.now(),
            'side': self.position_side,
            'entry_price': self.position_entry_price,
            'exit_price': self.position_entry_price + (pnl / self.position_size if self.position_size else 0),
            'position_size': self.position_size,
            'leverage': self.position_leverage,
            'pnl': pnl
        })
        logger.info(f"Trade closed - PnL: {pnl}, Total PnL: {self.total_pnl}")
    
    def close_position(self):
        """Reset position-related state variables."""
        self.active_position = False
        self.position_entry_price = 0.0
        self.position_entry_time = None
        self.position_size = 0.0
        self.position_leverage = 0
        self.position_side = None
        self.take_profit_price = 0.0
        self.stop_loss_price = 0.0
        
    def update_balance(self, balance: float):
        """Update current balance and set initial balance if not set yet."""
        if self.initial_balance == 0.0:
            self.initial_balance = balance
        self.current_balance = balance
        logger.info(f"Balance updated: {balance}")
        
    def get_status(self) -> Dict[str, Any]:
        """Return current trading status as a dictionary."""
        return {
            'active_position': self.active_position,
            'position_side': self.position_side,
            'position_entry_price': self.position_entry_price,
            'position_size': self.position_size,
            'position_leverage': self.position_leverage,
            'take_profit_price': self.take_profit_price,
            'stop_loss_price': self.stop_loss_price,
            'ai_confidence': self.ai_confidence,
            'current_balance': self.current_balance,
            'total_pnl': self.total_pnl,
            'daily_trades': self.daily_trades,
            'volatility': self.last_volatility
        }

# Technical indicators
def calculate_rsi(data: pd.DataFrame, period: int = 14) -> pd.Series:
    """Calculate Relative Strength Index."""
    delta = data['close'].diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    
    return rsi

def calculate_ema(data: pd.DataFrame, period: int) -> pd.Series:
    """Calculate Exponential Moving Average."""
    return data['close'].ewm(span=period, adjust=False).mean()

def calculate_volatility(data: pd.DataFrame, window: int = 20) -> float:
    """Calculate market volatility based on standard deviation of close prices."""
    return data['close'].pct_change().rolling(window=window).std().iloc[-1] * 100

def calculate_volume_profile(data: pd.DataFrame, window: int = 20) -> float:
    """Calculate if current volume is above average."""
    avg_volume = data['volume'].rolling(window=window).mean()
    current_volume = data['volume'].iloc[-1]
    return current_volume / avg_volume.iloc[-1] if not pd.isna(avg_volume.iloc[-1]) and avg_volume.iloc[-1] > 0 else 1.0

def calculate_macd(data: pd.DataFrame, fast_period: int = 12, slow_period: int = 26, signal_period: int = 9) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """Calculate MACD, MACD Signal and MACD Histogram."""
    ema_fast = data['close'].ewm(span=fast_period, adjust=False).mean()
    ema_slow = data['close'].ewm(span=slow_period, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    macd_signal = macd_line.ewm(span=signal_period, adjust=False).mean()
    macd_histogram = macd_line - macd_signal
    return macd_line, macd_signal, macd_histogram

def calculate_bollinger_bands(data: pd.DataFrame, window: int = 20, num_std: float = 2.0) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """Calculate Bollinger Bands."""
    sma = data['close'].rolling(window=window).mean()
    std = data['close'].rolling(window=window).std()
    upper_band = sma + (std * num_std)
    lower_band = sma - (std * num_std)
    return upper_band, sma, lower_band

def format_number(number: float, decimals: int = 8) -> str:
    """Format a number with specified decimal places without scientific notation."""
    return f"{number:.{decimals}f}".rstrip('0').rstrip('.') if '.' in f"{number:.{decimals}f}" else f"{int(number)}"

def format_price(symbol: str, price: float) -> str:
    """Format price based on the symbol's typical precision."""
    if 'BTC' in symbol:
        return format_number(price, 2)
    else:
        return format_number(price, 8)

def timestamp_to_datetime(timestamp: int) -> datetime:
    """Convert Unix timestamp to datetime."""
    return datetime.fromtimestamp(timestamp / 1000) if timestamp > 10**10 else datetime.fromtimestamp(timestamp)

def format_time(dt: datetime) -> str:
    """Format datetime to string."""
    return dt.strftime('%Y-%m-%d %H:%M:%S')

def retry(max_attempts: int = 3, delay: int = 2):
    """Retry decorator for API calls."""
    def decorator(func):
        def wrapper(*args, **kwargs):
            attempts = 0
            while attempts < max_attempts:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    attempts += 1
                    if attempts == max_attempts:
                        logger.error(f"Function {func.__name__} failed after {max_attempts} attempts. Error: {e}")
                        raise
                    logger.warning(f"Attempt {attempts} failed. Retrying in {delay} seconds... Error: {e}")
                    time.sleep(delay)
        return wrapper
    return decorator
