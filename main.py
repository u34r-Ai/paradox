import config
import logging
from app import app

if __name__ == "__main__":
    # Validate configuration
    if not config.validate_config():
        logging.error("Invalid configuration. Please check your environment variables.")
        exit(1)
        
    # Start the Flask app
    app.run(host='0.0.0.0', port=5000)
