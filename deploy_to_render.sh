#!/bin/bash

# Script to help deploy the crypto trading bot to Render
echo "Preparing for deployment to Render..."

# Check for git
if ! command -v git &> /dev/null; then
    echo "Git is required for deployment. Please install git."
    exit 1
fi

# Initialize git repo if it doesn't exist
if [ ! -d .git ]; then
    echo "Initializing git repository..."
    git init
    git add .
    git commit -m "Initial commit for Render deployment"
fi

# Create .gitignore if it doesn't exist
if [ ! -f .gitignore ]; then
    echo "Creating .gitignore file..."
    cat > .gitignore << EOL
__pycache__/
*.py[cod]
*$py.class
*.so
.env
.venv
env/
venv/
ENV/
env.bak/
venv.bak/
.DS_Store
*.log
EOL
fi

# Check if .env file exists and create from template if it doesn't
if [ ! -f .env ]; then
    echo "Creating .env file from template..."
    cp .env.template .env
    echo "Please edit the .env file with your actual API keys and settings"
fi

echo "Deployment preparation complete!"
echo ""
echo "Next steps:"
echo "1. Make sure your API keys and settings are in .env file"
echo "2. Create a GitHub repository and push this code to it"
echo "3. Sign up for a Render account at https://render.com"
echo "4. Create a new Web Service in Render dashboard, connecting to your GitHub repository"
echo "5. Configure your service with the environment variables from your .env file"
echo ""
echo "For detailed instructions, please refer to the README.md file."