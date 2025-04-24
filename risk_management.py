import logging
import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional, Any, Union
from datetime import datetime, timedelta
import config
from utils import TradingState, calculate_volatility

logger = logging.getLogger(__name__)

class RiskManager:
    def __init__(self, trading_state: TradingState):
        """Initialize risk manager with trading state reference."""
        self.state = trading_state
        self.max_drawdown = config.MAX_DRAWDOWN_PERCENTAGE / 100
        self.max_daily_trades = config.MAX_DAILY_TRADES
        self.max_open_positions = config.MAX_OPEN_POSITIONS
        self.min_leverage = config.MIN_LEVERAGE
        self.max_leverage = config.MAX_LEVERAGE
        self.stop_loss_pct = config.STOP_LOSS_PERCENTAGE / 100
        self.min_take_profit_pct = config.MIN_TAKE_PROFIT_PERCENTAGE / 100
        self.max_take_profit_pct = config.MAX_TAKE_PROFIT_PERCENTAGE / 100
        
    def calculate_ai_confidence(self, market_data: pd.DataFrame) -> float:
        """
        Calculate AI confidence score (0-1) based on multiple indicators.
        Higher confidence allows higher leverage.
        """
        # Indicators to consider:
        # 1. RSI (included in market_data)
        # 2. MACD crossover
        # 3. Volume profile
        # 4. Recent volatility
        # 5. Trend strength (EMAs)
        
        try:
            confidence_factors = []
            
            import random
            # Handle empty dataframe or missing data
            if market_data.empty or len(market_data) == 0:
                # Use fallback confidence value
                confidence = 0.85
                self.state.ai_confidence = confidence
                logger.info(f"AI confidence calculated: {confidence:.2f}")
                return confidence
            
            # Helper function to safely extract values and convert to float
            def safe_get_value(df, column):
                if column in df.columns and not df[column].empty:
                    value = df[column].iloc[-1]
                    # Convert NumPy types to Python native types
                    return float(value)
                return 0.5  # Default middle value
            
            # 1. RSI - more confidence near extremes (oversold for buy, overbought for sell)
            rsi = safe_get_value(market_data, 'rsi')
            if rsi < 30:  # Oversold
                confidence_factors.append(1 - (rsi / 30))  # Higher confidence as RSI gets lower
            elif rsi > 70:  # Overbought
                confidence_factors.append((rsi - 70) / 30)  # Higher confidence as RSI gets higher
            else:
                confidence_factors.append(0.3)  # Moderate confidence in middle range
            
            # 2. EMA alignment - check if short EMA above medium EMA above long EMA (or vice versa)
            ema_short = safe_get_value(market_data, 'ema_short')
            ema_medium = safe_get_value(market_data, 'ema_medium')
            ema_long = safe_get_value(market_data, 'ema_long')
            
            # For uptrend
            if ema_short > ema_medium > ema_long:
                confidence_factors.append(0.8)
            # For downtrend
            elif ema_short < ema_medium < ema_long:
                confidence_factors.append(0.8)
            # Partial alignment
            elif (ema_short > ema_medium) or (ema_medium > ema_long):
                confidence_factors.append(0.5)
            else:
                confidence_factors.append(0.3)
            
            # 3. Volume profile - higher volume increases confidence
            volume_factor = safe_get_value(market_data, 'volume_profile')
            confidence_factors.append(min(volume_factor / 2, 1.0))
            
            # 4. Volatility - moderate volatility is best
            volatility = safe_get_value(market_data, 'volatility')
            # Normalize volatility between 0-1 with peak at moderate volatility
            if volatility < 0.5:
                vol_confidence = volatility / 0.5  # Increases as volatility approaches 0.5%
            else:
                vol_confidence = max(0, 1 - ((volatility - 0.5) / 2))  # Decreases as volatility exceeds 0.5%
            confidence_factors.append(vol_confidence)
            
            # 5. Price relative to Bollinger Bands
            bb_position = safe_get_value(market_data, 'bb_position')
            if bb_position < 0.2 or bb_position > 0.8:
                confidence_factors.append(0.8)  # High confidence near bands
            else:
                confidence_factors.append(0.4)  # Lower confidence in middle
                
            # Calculate weighted average of confidence factors
            weights = [0.3, 0.2, 0.15, 0.15, 0.2]  # Weights for each factor
            confidence = sum(f * w for f, w in zip(confidence_factors, weights))
            
            # Adjust based on historical performance
            if self.state.total_pnl < 0:
                confidence *= 0.8  # Reduce confidence if losing
                
            # Store confidence for reference
            self.state.ai_confidence = min(confidence, 1.0)
            self.state.last_volatility = volatility
            
            logger.info(f"AI confidence calculated: {self.state.ai_confidence:.2f}")
            return self.state.ai_confidence
            
        except Exception as e:
            logger.error(f"Error calculating AI confidence: {e}")
            # Default to medium confidence if calculation fails
            self.state.ai_confidence = 0.5
            return 0.5
            
    def calculate_position_size(self, available_balance: float) -> float:
        """Calculate appropriate position size based on risk parameters."""
        position_size_pct = config.POSITION_SIZE_PERCENTAGE / 100
        
        # Adjust position size based on drawdown
        if self.state.total_pnl < 0 and self.state.initial_balance > 0:
            current_drawdown = abs(self.state.total_pnl) / self.state.initial_balance
            drawdown_factor = max(0.5, 1 - (current_drawdown / self.max_drawdown))
            position_size_pct *= drawdown_factor
            
        # Adjust based on daily trades
        daily_trades_factor = 1 - (self.state.daily_trades / self.max_daily_trades * 0.5)
        position_size_pct *= daily_trades_factor
        
        # Calculate final position size
        position_size = available_balance * position_size_pct
        
        logger.info(f"Calculated position size: {position_size:.4f} (from balance: {available_balance:.4f})")
        return position_size
        
    def calculate_leverage(self) -> int:
        """
        Calculate appropriate leverage based on AI confidence.
        Higher confidence -> higher leverage, within bounds.
        """
        # Linear mapping from confidence to leverage
        leverage = self.min_leverage + (self.state.ai_confidence * (self.max_leverage - self.min_leverage))
        leverage = round(leverage)  # Round to nearest integer
        
        # Ensure within bounds
        leverage = max(self.min_leverage, min(self.max_leverage, leverage))
        
        logger.info(f"Using leverage: {leverage}x (based on confidence: {self.state.ai_confidence:.2f})")
        return leverage
        
    def calculate_take_profit(self, entry_price: float, side: str, market_data: pd.DataFrame) -> float:
        """
        Calculate dynamic take profit based on volatility.
        Higher volatility -> higher take profit target.
        """
        # Extract and convert volatility to Python float
        try:
            if 'volatility' in market_data.columns and len(market_data['volatility']) > 0:
                volatility = float(market_data['volatility'].iloc[-1])
            else:
                # If no volatility data, use a default moderate value (0.5%)
                volatility = 0.5
        except (IndexError, AttributeError, TypeError):
            # Handle any errors by using default value
            volatility = 0.5
        
        # Scale take profit percentage based on volatility
        volatility_factor = min(1.0, volatility / 2)  # Cap at 100%
        take_profit_pct = self.min_take_profit_pct + (volatility_factor * (self.max_take_profit_pct - self.min_take_profit_pct))
        
        # Calculate take profit price
        if side == 'buy':
            take_profit_price = entry_price * (1 + take_profit_pct)
        else:  # sell
            take_profit_price = entry_price * (1 - take_profit_pct)
            
        logger.info(f"Take profit calculated: {take_profit_price:.2f} ({take_profit_pct*100:.1f}% from entry)")
        return take_profit_price
        
    def calculate_stop_loss(self, entry_price: float, side: str) -> float:
        """Calculate stop loss price based on configured percentage."""
        if side == 'buy':
            stop_loss_price = entry_price * (1 - self.stop_loss_pct)
        else:  # sell
            stop_loss_price = entry_price * (1 + self.stop_loss_pct)
            
        logger.info(f"Stop loss calculated: {stop_loss_price:.2f} ({self.stop_loss_pct*100:.1f}% from entry)")
        return stop_loss_price
        
    def can_open_position(self) -> bool:
        """Check if a new position can be opened based on risk parameters."""
        # Check if we already have an active position
        if self.state.active_position:
            logger.info("Cannot open new position: position already active")
            return False
            
        # Check if we've reached max daily trades
        if self.state.daily_trades >= self.max_daily_trades:
            logger.info(f"Cannot open new position: reached max daily trades ({self.max_daily_trades})")
            return False
            
        # Check drawdown limit
        if self.state.initial_balance > 0:
            current_drawdown = abs(min(0, self.state.total_pnl)) / self.state.initial_balance
            if current_drawdown >= self.max_drawdown:
                logger.info(f"Cannot open new position: max drawdown reached ({current_drawdown:.2%})")
                return False
        
        return True
        
    def should_reduce_risk(self) -> bool:
        """Check if risk should be reduced (e.g., smaller position sizes, lower leverage)."""
        # Check recent performance
        if len(self.state.trades_history) >= 3:
            recent_trades = self.state.trades_history[-3:]
            losses = sum(1 for trade in recent_trades if trade['pnl'] < 0)
            if losses >= 2:
                logger.info("Reducing risk due to recent losses")
                return True
                
        # Check drawdown
        if self.state.initial_balance > 0:
            current_drawdown = abs(min(0, self.state.total_pnl)) / self.state.initial_balance
            if current_drawdown > (self.max_drawdown * 0.7):  # If approaching max drawdown
                logger.info(f"Reducing risk due to drawdown approaching limit ({current_drawdown:.2%})")
                return True
                
        return False
        
    def prepare_market_data(self, ohlcv_data: pd.DataFrame, indicators: Dict[str, Any]) -> pd.DataFrame:
        """Prepare market data with indicators for risk assessment."""
        market_data = pd.DataFrame()
        market_data['close'] = ohlcv_data['close']
        
        # Add indicators
        market_data['rsi'] = indicators.get('rsi', pd.Series([50] * len(ohlcv_data)))
        market_data['ema_short'] = indicators.get('ema_short', pd.Series([0] * len(ohlcv_data)))
        market_data['ema_medium'] = indicators.get('ema_medium', pd.Series([0] * len(ohlcv_data)))
        market_data['ema_long'] = indicators.get('ema_long', pd.Series([0] * len(ohlcv_data)))
        
        # Calculate additional metrics
        market_data['volatility'] = calculate_volatility(ohlcv_data)
        market_data['volume_profile'] = indicators.get('volume_profile', pd.Series([1.0] * len(ohlcv_data)))
        
        # Calculate Bollinger Band position (0-1 where 0.5 is middle)
        if 'bb_upper' in indicators and 'bb_lower' in indicators:
            bb_upper = indicators['bb_upper']
            bb_lower = indicators['bb_lower']
            market_data['bb_position'] = (market_data['close'] - bb_lower) / (bb_upper - bb_lower)
        else:
            market_data['bb_position'] = pd.Series([0.5] * len(ohlcv_data))
            
        return market_data
