import logging
import time
import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional, Any, Union
from datetime import datetime, timedelta
import threading
import schedule
import config
from exchange_api import ExchangeAPI
from risk_management import RiskManager
from telegram_bot import TelegramBot
from utils import (
    TradingState, 
    calculate_rsi, 
    calculate_ema, 
    calculate_macd,
    calculate_bollinger_bands, 
    calculate_volatility,
    calculate_volume_profile
)

logger = logging.getLogger(__name__)

class TradingBot:
    def __init__(self):
        """Initialize the trading bot."""
        # Create state manager
        self.state = TradingState()
        
        # Initialize components
        self.exchange = ExchangeAPI(
            exchange_name=config.EXCHANGE_NAME,
            api_key=config.API_KEY,
            api_secret=config.API_SECRET
        )
        
        self.risk_manager = RiskManager(self.state)
        self.telegram = TelegramBot(self.state)
        
        # Trading parameters
        self.symbol = config.SYMBOL
        self.timeframe = config.TIMEFRAME
        self.loop_interval = config.LOOP_INTERVAL
        self.trading_active = config.TRADING_ACTIVE
        
        # Trading thread
        self.trading_thread = None
        self.stop_event = threading.Event()
        
        logger.info(f"Trading bot initialized for {self.symbol} on {config.EXCHANGE_NAME}")
    
    def start(self):
        """Start the trading bot."""
        # Start Telegram bot if configured
        if config.TELEGRAM_TOKEN and config.TELEGRAM_CHAT_ID:
            if not self.telegram.start():
                logger.error("Failed to start Telegram bot")
        
        # Check exchange connection
        if not self.exchange.is_connected():
            error_msg = "Cannot connect to exchange. Check API credentials and network."
            logger.error(error_msg)
            self.telegram.notify_error(error_msg)
            return False
        
        # Get initial account balance
        try:
            balance = self.exchange.fetch_balance()
            quote_currency = self.symbol.split('/')[1]
            available_balance = balance.get('free', {}).get(quote_currency, 0)
            
            self.state.update_balance(available_balance)
            logger.info(f"Initial balance: {available_balance} {quote_currency}")
        except Exception as e:
            error_msg = f"Failed to get initial balance: {e}"
            logger.error(error_msg)
            self.telegram.notify_error(error_msg)
            return False
        
        # Start trading loop in separate thread
        self.trading_thread = threading.Thread(target=self._trading_loop)
        self.trading_thread.daemon = True
        self.trading_thread.start()
        
        # Schedule daily reset
        schedule.every().day.at("00:00").do(self.state.reset_daily_trades)
        
        logger.info("Trading bot started successfully")
        self.telegram.send_system_status()
        return True
    
    def stop(self):
        """Stop the trading bot."""
        logger.info("Stopping trading bot...")
        self.stop_event.set()
        
        if self.trading_thread and self.trading_thread.is_alive():
            self.trading_thread.join(timeout=10)
        
        self.telegram.stop()
        logger.info("Trading bot stopped")
    
    def _trading_loop(self):
        """Main trading loop that runs continuously."""
        while not self.stop_event.is_set():
            try:
                # Update account balance
                balance = self.exchange.fetch_balance()
                quote_currency = self.symbol.split('/')[1]
                available_balance = balance.get('free', {}).get(quote_currency, 0)
                self.state.update_balance(available_balance)
                
                # Run scheduler
                schedule.run_pending()
                
                # Fetch market data
                ohlcv_data = self.exchange.fetch_ohlcv(self.symbol, self.timeframe, limit=100)
                
                # Calculate indicators
                indicators = self._calculate_indicators(ohlcv_data)
                
                # Prepare market data for risk assessment
                market_data = self.risk_manager.prepare_market_data(ohlcv_data, indicators)
                
                # Calculate AI confidence
                self.risk_manager.calculate_ai_confidence(market_data)
                
                # Update health check timestamp
                self.state.last_check_time = datetime.now()
                
                # Check for exit conditions if we have an active position
                if self.state.active_position:
                    self._check_exit_conditions(ohlcv_data.iloc[-1]['close'])
                
                # Check for entry conditions if we don't have an active position
                elif self.trading_active and self.risk_manager.can_open_position():
                    self._check_entry_conditions(ohlcv_data, indicators)
                
                # Sleep for the specified interval
                time.sleep(self.loop_interval)
                
            except Exception as e:
                logger.error(f"Error in trading loop: {e}")
                self.telegram.notify_error(f"Trading loop error: {e}")
                time.sleep(30)  # Wait before retrying
    
    def _calculate_indicators(self, ohlcv_data: pd.DataFrame) -> Dict[str, Any]:
        """Calculate technical indicators from OHLCV data."""
        indicators = {}
        
        # Calculate RSI
        indicators['rsi'] = calculate_rsi(ohlcv_data, period=config.RSI_PERIOD)
        
        # Calculate EMAs
        indicators['ema_short'] = calculate_ema(ohlcv_data, period=config.EMA_SHORT)
        indicators['ema_medium'] = calculate_ema(ohlcv_data, period=config.EMA_MEDIUM)
        indicators['ema_long'] = calculate_ema(ohlcv_data, period=config.EMA_LONG)
        
        # Calculate MACD
        indicators['macd'], indicators['macd_signal'], indicators['macd_hist'] = calculate_macd(ohlcv_data)
        
        # Calculate Bollinger Bands
        indicators['bb_upper'], indicators['bb_middle'], indicators['bb_lower'] = calculate_bollinger_bands(ohlcv_data)
        
        # Calculate Volume Profile
        indicators['volume_profile'] = calculate_volume_profile(ohlcv_data)
        
        # Calculate Volatility
        indicators['volatility'] = calculate_volatility(ohlcv_data)
        
        return indicators
    
    def _check_entry_conditions(self, ohlcv_data: pd.DataFrame, indicators: Dict[str, Any]):
        """Check if entry conditions are met and open a position if appropriate."""
        try:
            # Get the latest data - convert to native Python types to avoid NumPy float issues
            latest_close = float(ohlcv_data['close'].iloc[-1])
            latest_rsi = float(indicators['rsi'].iloc[-1])
            latest_ema_short = float(indicators['ema_short'].iloc[-1])
            latest_ema_medium = float(indicators['ema_medium'].iloc[-1])
            latest_ema_long = float(indicators['ema_long'].iloc[-1])
            latest_macd = float(indicators['macd'].iloc[-1])
            latest_macd_signal = float(indicators['macd_signal'].iloc[-1])
            latest_macd_hist = float(indicators['macd_hist'].iloc[-1])
            
            # Handle volatility which might be a scalar NumPy value
            volatility = indicators['volatility']
            if hasattr(volatility, 'iloc'):
                volatility = float(volatility.iloc[-1])
            else:
                volatility = float(volatility)
                
            # Handle volume profile which might be a scalar NumPy value
            volume_profile = indicators['volume_profile']
            if hasattr(volume_profile, 'iloc'):
                volume_profile = float(volume_profile.iloc[-1])
            else:
                volume_profile = float(volume_profile)
            
            # Determine trading signals
            buy_signal = False
            sell_signal = False
            
            # Buy signal criteria:
            # 1. RSI crosses above oversold threshold
            # 2. Short EMA crosses above medium EMA (confirming uptrend)
            # 3. MACD histogram is positive (momentum is positive)
            # 4. Price is above long-term EMA (overall uptrend)
            buy_criteria = [
                latest_rsi > config.RSI_OVERSOLD,
                latest_rsi < 60,  # Not getting overbought
                latest_ema_short > latest_ema_medium,
                latest_macd_hist > 0,
                latest_close > latest_ema_long,
                volume_profile > config.VOLUME_THRESHOLD
            ]
            
            if (latest_rsi > config.RSI_OVERSOLD and latest_rsi < 60 and 
                latest_ema_short > latest_ema_medium and
                latest_macd > latest_macd_signal and
                latest_close > latest_ema_long and
                volume_profile > config.VOLUME_THRESHOLD):
                buy_signal = True
                
            # Sell signal criteria:
            # 1. RSI crosses below overbought threshold
            # 2. Short EMA crosses below medium EMA (confirming downtrend)
            # 3. MACD histogram is negative (momentum is negative)
            # 4. Price is below long-term EMA (overall downtrend)
            if (latest_rsi < config.RSI_OVERBOUGHT and latest_rsi > 40 and 
                latest_ema_short < latest_ema_medium and
                latest_macd < latest_macd_signal and
                latest_close < latest_ema_long and
                volume_profile > config.VOLUME_THRESHOLD):
                sell_signal = True
            
            # Apply trading actions based on signals
            if buy_signal or sell_signal:
                side = 'buy' if buy_signal else 'sell'
                
                # Calculate position size
                available_balance = self.state.current_balance
                position_size = self.risk_manager.calculate_position_size(available_balance)
                
                # Calculate leverage
                leverage = self.risk_manager.calculate_leverage()
                
                # Calculate entry price (use market price)
                entry_price = latest_close
                
                # Calculate stop loss and take profit prices
                stop_loss = self.risk_manager.calculate_stop_loss(entry_price, side)
                take_profit = self.risk_manager.calculate_take_profit(entry_price, side, pd.DataFrame({
                    'volatility': [volatility]
                }))
                
                logger.info(f"Opening {side} position: {position_size} at {entry_price} with {leverage}x leverage")
                
                # Open the position
                order = self.exchange.create_market_order(
                    symbol=self.symbol,
                    side=side,
                    amount=position_size / entry_price,  # Convert to base currency units
                    leverage=leverage,
                    stop_loss=stop_loss,
                    take_profit=take_profit
                )
                
                # Update state
                self.state.active_position = True
                self.state.position_side = side
                self.state.position_entry_price = entry_price
                self.state.position_entry_time = datetime.now()
                self.state.position_size = position_size
                self.state.position_leverage = leverage
                self.state.take_profit_price = take_profit
                self.state.stop_loss_price = stop_loss
                self.state.daily_trades += 1
                
                # Notify via Telegram
                self.telegram.notify_trade_opened(
                    symbol=self.symbol,
                    side=side,
                    size=position_size / entry_price,
                    price=entry_price,
                    leverage=leverage
                )
                
                logger.info(f"Position opened: {side} {position_size / entry_price} {self.symbol} at {entry_price}")
                
        except Exception as e:
            logger.error(f"Error checking entry conditions: {e}")
            self.telegram.notify_error(f"Error opening position: {e}")
    
    def _check_exit_conditions(self, current_price: float):
        """Check if exit conditions are met and close the position if appropriate."""
        if not self.state.active_position:
            return
            
        try:
            # Ensure current_price is a Python float
            current_price = float(current_price)
            
            # Ensure take_profit_price and stop_loss_price are Python floats
            take_profit_price = float(self.state.take_profit_price)
            stop_loss_price = float(self.state.stop_loss_price)
            
            # Check if take profit hit
            take_profit_hit = False
            if self.state.position_side == 'buy' and current_price >= take_profit_price:
                take_profit_hit = True
            elif self.state.position_side == 'sell' and current_price <= take_profit_price:
                take_profit_hit = True
                
            # Check if stop loss hit
            stop_loss_hit = False
            if self.state.position_side == 'buy' and current_price <= stop_loss_price:
                stop_loss_hit = True
            elif self.state.position_side == 'sell' and current_price >= stop_loss_price:
                stop_loss_hit = True
                
            # Check if position is old enough to consider closing
            time_exit = False
            if self.state.position_entry_time:
                hours_open = (datetime.now() - self.state.position_entry_time).total_seconds() / 3600
                if hours_open > 24:  # Close positions after 24 hours
                    time_exit = True
                    
            # Close position if any exit condition is met
            if take_profit_hit or stop_loss_hit or time_exit:
                exit_reason = "take profit" if take_profit_hit else ("stop loss" if stop_loss_hit else "time exit")
                logger.info(f"Closing position: {exit_reason}")
                
                # Execute the close order
                close_side = 'sell' if self.state.position_side == 'buy' else 'buy'
                position_size_base = self.state.position_size / self.state.position_entry_price
                
                order = self.exchange.create_market_order(
                    symbol=self.symbol,
                    side=close_side,
                    amount=position_size_base,
                    leverage=self.state.position_leverage
                )
                
                # Calculate PnL
                if self.state.position_side == 'buy':
                    pnl = (current_price - self.state.position_entry_price) * position_size_base * self.state.position_leverage
                else:
                    pnl = (self.state.position_entry_price - current_price) * position_size_base * self.state.position_leverage
                    
                # Calculate ROI percentage
                roi_percentage = (pnl / self.state.position_size) * 100
                
                # Update state
                self.state.update_pnl(pnl)
                
                # Notify via Telegram
                self.telegram.notify_trade_closed(
                    symbol=self.symbol,
                    side=self.state.position_side,
                    entry_price=self.state.position_entry_price,
                    exit_price=current_price,
                    pnl=pnl,
                    roi_percentage=roi_percentage
                )
                
                # Reset position state
                self.state.close_position()
                
                logger.info(f"Position closed - PnL: {pnl}, ROI: {roi_percentage}%")
                
        except Exception as e:
            logger.error(f"Error checking exit conditions: {e}")
            self.telegram.notify_error(f"Error closing position: {e}")
