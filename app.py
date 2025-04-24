import logging
import time
import threading
import config
from trading_bot import TradingBot
from flask import Flask, render_template, jsonify, request, redirect, url_for
import os

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

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "default_secret_key")

# Create trading bot instance
trading_bot = None

@app.route('/')
def home():
    """Home page with basic status information."""
    if trading_bot and trading_bot.state:
        status = trading_bot.state.get_status()
        trading_enabled = config.TRADING_ACTIVE
        return jsonify({
            'status': 'running',
            'trading_enabled': trading_enabled,
            'trading_state': status
        })
    else:
        return jsonify({
            'status': 'not_running',
            'error': 'Trading bot not initialized'
        })
        
@app.route('/ping')
def ping():
    """Simple ping endpoint to keep the service alive on Render."""
    return jsonify({
        'status': 'ok',
        'timestamp': time.time()
    })
    
@app.route('/status')
def status():
    """Health check endpoint for Render."""
    if trading_bot and trading_bot.state:
        return jsonify({
            'status': 'healthy',
            'bot_running': True,
            'last_update': trading_bot.state.last_check_time
        }), 200
    else:
        # Still return 200 for health check to pass
        return jsonify({
            'status': 'healthy',
            'bot_running': False
        }), 200

@app.route('/api/start', methods=['POST'])
def start_trading():
    """API endpoint to start the trading bot."""
    global trading_bot
    
    if trading_bot is None:
        try:
            # Validate configuration
            if not config.validate_config():
                return jsonify({
                    'success': False,
                    'message': 'Invalid configuration. Check log for details.'
                })
            
            # Initialize and start trading bot
            trading_bot = TradingBot()
            result = trading_bot.start()
            
            if result:
                return jsonify({
                    'success': True,
                    'message': 'Trading bot started successfully'
                })
            else:
                return jsonify({
                    'success': False,
                    'message': 'Failed to start trading bot. Check logs for details.'
                })
                
        except Exception as e:
            logger.error(f"Error starting trading bot: {e}")
            return jsonify({
                'success': False,
                'message': f'Error: {e}'
            })
    else:
        return jsonify({
            'success': False,
            'message': 'Trading bot already running'
        })

@app.route('/api/stop', methods=['POST'])
def stop_trading():
    """API endpoint to stop the trading bot."""
    global trading_bot
    
    if trading_bot is not None:
        try:
            trading_bot.stop()
            trading_bot = None
            return jsonify({
                'success': True,
                'message': 'Trading bot stopped successfully'
            })
        except Exception as e:
            logger.error(f"Error stopping trading bot: {e}")
            return jsonify({
                'success': False,
                'message': f'Error: {e}'
            })
    else:
        return jsonify({
            'success': False,
            'message': 'Trading bot is not running'
        })

@app.route('/api/status')
def get_status():
    """API endpoint to get current trading status."""
    if trading_bot and trading_bot.state:
        return jsonify({
            'success': True,
            'status': trading_bot.state.get_status(),
            'telegram_connected': trading_bot.telegram.is_running()
        })
    else:
        return jsonify({
            'success': False,
            'message': 'Trading bot not initialized'
        })

@app.route('/api/trades')
def get_trades():
    """API endpoint to get trade history."""
    if trading_bot and trading_bot.state:
        return jsonify({
            'success': True,
            'trades': [
                {
                    'time': trade['time'].strftime('%Y-%m-%d %H:%M:%S'),
                    'side': trade['side'],
                    'entry_price': trade['entry_price'],
                    'exit_price': trade['exit_price'],
                    'position_size': trade['position_size'],
                    'leverage': trade['leverage'],
                    'pnl': trade['pnl']
                }
                for trade in trading_bot.state.trades_history
            ]
        })
    else:
        return jsonify({
            'success': False,
            'message': 'Trading bot not initialized'
        })

@app.route('/api/config')
def get_config():
    """API endpoint to get current configuration."""
    return jsonify({
        'success': True,
        'config': config.get_trading_params()
    })

def start_bot_on_startup():
    """Start the trading bot when the application starts."""
    global trading_bot
    
    # Wait a bit to ensure app is fully initialized
    time.sleep(5)
    
    try:
        # Validate configuration
        if not config.validate_config():
            logger.error("Invalid configuration. Trading bot not started.")
            return
        
        # Initialize and start trading bot
        trading_bot = TradingBot()
        result = trading_bot.start()
        
        if result:
            logger.info("Trading bot started automatically on application startup")
        else:
            logger.error("Failed to start trading bot automatically")
                
    except Exception as e:
        logger.error(f"Error starting trading bot on startup: {e}")

# Start the trading bot in a separate thread when the app starts
startup_thread = threading.Thread(target=start_bot_on_startup)
startup_thread.daemon = True
startup_thread.start()

if __name__ == '__main__':
    # Start the Flask app
    app.run(host='0.0.0.0', port=5000, debug=True)
