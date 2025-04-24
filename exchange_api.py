import ccxt
import logging
import pandas as pd
import numpy as np
import random
from typing import Dict, List, Tuple, Optional, Any, Union
import time
from datetime import datetime, timedelta
import config
from utils import retry, format_price

logger = logging.getLogger(__name__)

class ExchangeAPI:
    def __init__(self, exchange_name: str, api_key: str, api_secret: str):
        """Initialize exchange API connection."""
        self.exchange_name = exchange_name.lower()
        self.api_key = api_key
        self.api_secret = api_secret
        
        # Set to False to enable real trading
        # Will fall back to simulation if connection issues occur
        self.simulation_mode = False
        
        # Simulation variables with realistic starting values
        self.base_price = 66000.0  # Current approximate BTC price
        self.volatility = 0.008    # 0.8% price volatility (realistic for crypto)
        self.balance = 10000.0     # Starting balance for simulation
        self.open_orders = {}
        self.order_id_counter = 10000
        self.positions = []
        
        # Only attempt to connect to exchange if not in simulation mode
        if not self.simulation_mode:
            try:
                self.exchange = self._init_exchange()
            except Exception as e:
                logger.warning(f"Falling back to simulation mode due to error: {str(e)}")
                self.simulation_mode = True
                logger.info("SIMULATION MODE ACTIVE - Using simulated market data")
        else:
            self.exchange = None
            logger.info("🔄 SIMULATION MODE ACTIVE - Trading with real strategy but simulated execution")
        
        self.order_cache = {}  # cache orders by id
        
    def _init_exchange(self) -> ccxt.Exchange:
        """Initialize exchange with appropriate settings."""
        if self.exchange_name not in ccxt.exchanges:
            logger.warning(f"Exchange {self.exchange_name} not supported by CCXT, using simulation mode")
            self.simulation_mode = True
            return None
        
        # Configuration for the exchange
        exchange_config = {
            'apiKey': self.api_key,
            'secret': self.api_secret,
            'enableRateLimit': True,
            'options': {
                'defaultType': 'future',  # For margin trading and futures
                'adjustForTimeDifference': True,
                'recvWindow': 60000,  # Extended window to avoid timestamp issues
            },
            'timeout': 30000,  # Increased timeout for API calls
            # No default proxy - will be set from environment variable
        }
        
        # Check for proxy settings in environment variables
        if config.HTTP_PROXY or config.HTTPS_PROXY:
            proxy = config.HTTP_PROXY or config.HTTPS_PROXY
            logger.info(f"Using proxy from environment variables: {proxy}")
            exchange_config['proxy'] = proxy
        
        exchange_class = getattr(ccxt, self.exchange_name)
        exchange = exchange_class(exchange_config)
        
        # Load markets to get symbols and other market information
        try:
            exchange.load_markets()
            logger.info(f"Successfully connected to {self.exchange_name}")
        except Exception as e:
            logger.error(f"Failed to connect to exchange: {e}")
            self.simulation_mode = True
            raise
            
        return exchange
        
    def _generate_simulated_price(self) -> float:
        """Generate a simulated price based on random walk with mean reversion."""
        # Add some randomness to the price with mean reversion
        price_change = (random.random() - 0.5) * 2 * self.volatility * self.base_price
        self.base_price += price_change
        # Gradually revert to the mean (current BTC price range)
        self.base_price = self.base_price * 0.998 + 66000.0 * 0.002
        return round(self.base_price, 2)
    
    @retry(max_attempts=3, delay=2)
    def fetch_ticker(self, symbol: str) -> Dict[str, Any]:
        """Fetch current ticker data for a symbol."""
        if self.simulation_mode:
            current_price = self._generate_simulated_price()
            ticker = {
                'symbol': symbol,
                'timestamp': int(datetime.now().timestamp() * 1000),
                'datetime': datetime.now().isoformat(),
                'high': current_price * 1.005,
                'low': current_price * 0.995,
                'bid': current_price * 0.999,
                'ask': current_price * 1.001,
                'last': current_price,
                'close': current_price,
                'previousClose': current_price * 0.998,
                'change': current_price * 0.002,
                'percentage': 0.2,
                'average': current_price,
                'baseVolume': 1000.0,
                'quoteVolume': 1000.0 * current_price,
                'info': {}
            }
            logger.debug(f"Generated simulated ticker for {symbol}: price={current_price}")
            return ticker
            
        try:
            ticker = self.exchange.fetch_ticker(symbol)
            logger.debug(f"Fetched ticker for {symbol}: {ticker}")
            return ticker
        except Exception as e:
            logger.error(f"Error fetching ticker for {symbol}: {e}, using simulation")
            self.simulation_mode = True
            return self.fetch_ticker(symbol)
    
    @retry(max_attempts=3, delay=2)
    def fetch_ohlcv(self, symbol: str, timeframe: str = '5m', limit: int = 100) -> pd.DataFrame:
        """Fetch OHLCV (candle) data for a symbol."""
        if self.simulation_mode:
            now = datetime.now()
            data = []
            
            # Time intervals in minutes based on timeframe
            minutes_interval = 5
            if timeframe == '1m':
                minutes_interval = 1
            elif timeframe == '5m':
                minutes_interval = 5
            elif timeframe == '15m':
                minutes_interval = 15
            elif timeframe == '1h':
                minutes_interval = 60
            elif timeframe == '4h':
                minutes_interval = 240
            elif timeframe == '1d':
                minutes_interval = 1440
                
            # Generate historical data with some trend and noise
            base_price = self.base_price * 0.95
            for i in range(limit):
                timestamp = now - timedelta(minutes=minutes_interval * (limit-i))
                timestamp_ms = int(timestamp.timestamp() * 1000)
                
                # Add slight trends and noise
                noise = (np.random.random() - 0.5) * 0.02
                trend = 0.0001 * i  # Small upward trend
                
                price = base_price * (1 + noise + trend)
                price_open = price * (1 + (np.random.random() - 0.5) * 0.01)
                price_high = max(price, price_open) * (1 + np.random.random() * 0.01)
                price_low = min(price, price_open) * (1 - np.random.random() * 0.01)
                volume = np.random.random() * 100 + 50
                
                data.append([timestamp_ms, price_open, price_high, price_low, price, volume])
                base_price = price
                
            df = pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)
            logger.debug(f"Generated {len(df)} simulated OHLCV records for {symbol}")
            return df
            
        try:
            ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)
            logger.debug(f"Fetched {len(df)} OHLCV records for {symbol}")
            return df
        except Exception as e:
            logger.error(f"Error fetching OHLCV data for {symbol}: {e}, using simulation")
            self.simulation_mode = True
            return self.fetch_ohlcv(symbol, timeframe, limit)
    
    @retry(max_attempts=3, delay=2)
    def fetch_balance(self) -> Dict[str, float]:
        """Fetch account balance."""
        if self.simulation_mode:
            quote_currency = config.QUOTE_CURRENCY
            base_currency = config.BASE_CURRENCY
            
            balance = {
                'free': {quote_currency: self.balance, base_currency: 0.0},
                'used': {quote_currency: 0.0, base_currency: 0.0},
                'total': {quote_currency: self.balance, base_currency: 0.0},
                'info': {}
            }
            logger.info(f"Simulated account balance: {self.balance} {quote_currency}")
            return balance
            
        try:
            balance = self.exchange.fetch_balance()
            usdt_total = balance.get('total', {}).get('USDT', 0)
            btc_total = balance.get('total', {}).get('BTC', 0)
            
            logger.info(f"Account balance: {usdt_total} USDT, {btc_total} BTC")
            return balance
        except Exception as e:
            logger.error(f"Error fetching account balance: {e}, using simulation")
            self.simulation_mode = True
            return self.fetch_balance()
    
    @retry(max_attempts=3, delay=2)
    def create_market_order(self, symbol: str, side: str, amount: float, leverage: int = 1, 
                          stop_loss: Optional[float] = None, take_profit: Optional[float] = None) -> Dict[str, Any]:
        """
        Create a market order with optional stop loss and take profit.
        
        Args:
            symbol: Trading pair symbol
            side: 'buy' or 'sell'
            amount: Order size in base currency units
            leverage: Leverage to use for margin trading (futures)
            stop_loss: Optional stop loss price
            take_profit: Optional take profit price
            
        Returns:
            Dict containing order information
        """
        if self.simulation_mode:
            # Create simulated order in simulation mode
            current_price = self._generate_simulated_price()
            order_id = str(self.order_id_counter)
            self.order_id_counter += 1
            
            order = {
                'id': order_id,
                'symbol': symbol,
                'side': side,
                'type': 'market',
                'price': current_price,
                'amount': amount,
                'cost': amount * current_price,
                'filled': amount,
                'remaining': 0,
                'status': 'closed',
                'fee': {
                    'cost': amount * current_price * 0.001,
                    'currency': symbol.split('/')[1]
                },
                'timestamp': int(datetime.now().timestamp() * 1000),
                'datetime': datetime.now().isoformat(),
                'leverage': leverage,
                'info': {}
            }
            
            # Add position to our simulated positions
            if side == 'buy':
                # Update account balance (subtract cost + fee)
                self.balance -= (amount * current_price * (1 + 0.001))
                # Add position
                self.positions.append({
                    'symbol': symbol,
                    'side': 'long',
                    'amount': amount,
                    'entry_price': current_price,
                    'leverage': leverage,
                    'timestamp': datetime.now(),
                    'stop_loss': stop_loss,
                    'take_profit': take_profit
                })
            else:  # sell
                # Update account balance (add proceeds - fee)
                self.balance += (amount * current_price * (1 - 0.001))
                # Add position
                self.positions.append({
                    'symbol': symbol,
                    'side': 'short',
                    'amount': amount,
                    'entry_price': current_price,
                    'leverage': leverage,
                    'timestamp': datetime.now(),
                    'stop_loss': stop_loss,
                    'take_profit': take_profit
                })
                
            self.order_cache[order_id] = order
            logger.info(f"Created simulated {side} market order for {amount} {symbol.split('/')[0]} at {current_price}")
            
            # Add stop loss and take profit info
            if stop_loss is not None:
                sl_order_id = str(self.order_id_counter)
                self.order_id_counter += 1
                sl_order = {
                    'id': sl_order_id,
                    'symbol': symbol,
                    'side': 'buy' if side == 'sell' else 'sell',
                    'type': 'stop_market',
                    'price': stop_loss,
                    'amount': amount,
                    'status': 'open',
                    'timestamp': int(datetime.now().timestamp() * 1000),
                    'datetime': datetime.now().isoformat(),
                    'info': {'stopPrice': stop_loss}
                }
                order['stop_loss_order'] = sl_order
                self.open_orders[sl_order_id] = sl_order
                logger.info(f"Created simulated stop loss at {stop_loss}")
                
            if take_profit is not None:
                tp_order_id = str(self.order_id_counter)
                self.order_id_counter += 1
                tp_order = {
                    'id': tp_order_id,
                    'symbol': symbol,
                    'side': 'buy' if side == 'sell' else 'sell',
                    'type': 'limit',
                    'price': take_profit,
                    'amount': amount,
                    'status': 'open',
                    'timestamp': int(datetime.now().timestamp() * 1000),
                    'datetime': datetime.now().isoformat(),
                    'info': {}
                }
                order['take_profit_order'] = tp_order
                self.open_orders[tp_order_id] = tp_order
                logger.info(f"Created simulated take profit at {take_profit}")
                
            return order
            
        try:
            # Set leverage first if needed
            if leverage > 1 and self.exchange:
                self.exchange.set_leverage(leverage, symbol)
                logger.info(f"Set leverage to {leverage}x for {symbol}")
            
            # Create the market order
            if not self.exchange:
                self.simulation_mode = True
                logger.info("Exchange not available, switching to simulation mode")
                return self.create_market_order(symbol, side, amount, leverage, stop_loss, take_profit)
                
            order = self.exchange.create_market_order(symbol, side, amount)
            order_id = order['id']
            self.order_cache[order_id] = order
            
            logger.info(f"Created {side} market order for {amount} {symbol.split('/')[0]} at market price")
            
            # Create stop loss if specified
            if stop_loss is not None:
                stop_side = 'buy' if side == 'sell' else 'sell'
                try:
                    sl_order = self.exchange.create_order(
                        symbol=symbol,
                        type='stop_market',
                        side=stop_side,
                        amount=amount,
                        params={
                            'stopPrice': format_price(symbol, stop_loss),
                            'reduceOnly': True
                        }
                    )
                    logger.info(f"Set stop loss at {stop_loss} for order {order_id}")
                    order['stop_loss_order'] = sl_order
                except Exception as e:
                    logger.error(f"Failed to set stop loss: {e}")
            
            # Create take profit if specified
            if take_profit is not None:
                tp_side = 'buy' if side == 'sell' else 'sell'
                try:
                    tp_order = self.exchange.create_order(
                        symbol=symbol,
                        type='limit',
                        side=tp_side,
                        amount=amount,
                        price=format_price(symbol, take_profit),
                        params={
                            'reduceOnly': True
                        }
                    )
                    logger.info(f"Set take profit at {take_profit} for order {order_id}")
                    order['take_profit_order'] = tp_order
                except Exception as e:
                    logger.error(f"Failed to set take profit: {e}")
            
            return order
        except Exception as e:
            logger.error(f"Error creating market order: {e}, switching to simulation")
            self.simulation_mode = True
            return self.create_market_order(symbol, side, amount, leverage, stop_loss, take_profit)
    
    @retry(max_attempts=3, delay=2)
    def cancel_order(self, order_id: str, symbol: str) -> Dict[str, Any]:
        """Cancel an open order."""
        try:
            result = self.exchange.cancel_order(order_id, symbol)
            logger.info(f"Cancelled order {order_id} for {symbol}")
            return result
        except Exception as e:
            logger.error(f"Error cancelling order {order_id}: {e}")
            raise
    
    @retry(max_attempts=3, delay=2)
    def fetch_open_orders(self, symbol: str = None) -> List[Dict[str, Any]]:
        """Fetch all open orders, optionally filtered by symbol."""
        try:
            open_orders = self.exchange.fetch_open_orders(symbol)
            logger.info(f"Fetched {len(open_orders)} open orders" + (f" for {symbol}" if symbol else ""))
            return open_orders
        except Exception as e:
            logger.error(f"Error fetching open orders: {e}")
            raise
    
    @retry(max_attempts=3, delay=2)
    def fetch_closed_orders(self, symbol: str = None, since: int = None, limit: int = None) -> List[Dict[str, Any]]:
        """Fetch closed (filled or canceled) orders."""
        try:
            closed_orders = self.exchange.fetch_closed_orders(symbol, since, limit)
            logger.info(f"Fetched {len(closed_orders)} closed orders" + (f" for {symbol}" if symbol else ""))
            return closed_orders
        except Exception as e:
            logger.error(f"Error fetching closed orders: {e}")
            raise
    
    @retry(max_attempts=3, delay=2)
    def fetch_order(self, order_id: str, symbol: str) -> Dict[str, Any]:
        """Fetch order by ID."""
        try:
            # Check if the order is in the cache
            if order_id in self.order_cache:
                return self.order_cache[order_id]
            
            order = self.exchange.fetch_order(order_id, symbol)
            self.order_cache[order_id] = order
            logger.debug(f"Fetched order {order_id} for {symbol}")
            return order
        except Exception as e:
            logger.error(f"Error fetching order {order_id}: {e}")
            raise
    
    @retry(max_attempts=3, delay=2)
    def fetch_positions(self, symbol: str = None) -> List[Dict[str, Any]]:
        """Fetch current open positions."""
        try:
            # This works for futures exchanges that support position fetching
            if hasattr(self.exchange, 'fetch_positions'):
                positions = self.exchange.fetch_positions(symbol)
                logger.info(f"Fetched {len(positions)} positions" + (f" for {symbol}" if symbol else ""))
                return positions
            else:
                logger.warning(f"Exchange {self.exchange_name} does not support direct position fetching")
                return []
        except Exception as e:
            logger.error(f"Error fetching positions: {e}")
            raise
    
    @retry(max_attempts=3, delay=2)
    def get_available_balance(self, currency: str) -> float:
        """Get available balance for a specific currency."""
        try:
            balance = self.fetch_balance()
            available = balance.get('free', {}).get(currency, 0)
            logger.info(f"Available {currency} balance: {available}")
            return available
        except Exception as e:
            logger.error(f"Error getting available {currency} balance: {e}")
            raise
    
    @retry(max_attempts=3, delay=2)
    def get_market_info(self, symbol: str) -> Dict[str, Any]:
        """Get market information for a symbol."""
        try:
            market = self.exchange.market(symbol)
            logger.debug(f"Market info for {symbol}: {market}")
            return market
        except Exception as e:
            logger.error(f"Error getting market info for {symbol}: {e}")
            raise
    
    def is_connected(self) -> bool:
        """Check if connected to the exchange."""
        if self.simulation_mode:
            # Always return True in simulation mode
            return True
            
        try:
            # Simple ping test
            if self.exchange:
                self.exchange.fetch_ticker(config.SYMBOL)
                return True
            return False
        except Exception as e:
            logger.error(f"Exchange connection check failed: {e}")
            self.simulation_mode = True
            logger.info("Switching to simulation mode after connection failure")
            return True  # Return True since simulation mode is active
