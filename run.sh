
## 10. run.sh
```bash
#!/bin/bash

# Food Recipe Bot Startup Script
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if .env file exists
if [ ! -f .env ]; then
    print_warning ".env file not found. Creating from .env.example..."
    cp .env.example .env
    print_status "Please edit .env file with your API keys and restart the script."
    exit 1
fi

# Load environment variables
export $(grep -v '^#' .env | xargs)

# Function to check if a command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to check if a port is in use
port_in_use() {
    netstat -tuln | grep -q ":$1 "
}

# Main execution
case "${1:-}" in
    "docker")
        print_status "Starting with Docker Compose..."
        if ! command_exists docker; then
            print_error "Docker is not installed. Please install Docker first."
            exit 1
        fi
        
        if ! command_exists docker-compose; then
            print_error "Docker Compose is not installed. Please install it first."
            exit 1
        fi
        
        docker-compose up --build
        ;;
    
    "backend")
        print_status "Starting Backend API..."
        cd backend
        
        if port_in_use 8000; then
            print_error "Port 8000 is already in use. Please free the port and try again."
            exit 1
        fi
        
        if [ "$ENVIRONMENT" = "production" ]; then
            uvicorn app:app --host 0.0.0.0 --port 8000
        else
            uvicorn app:app --host 0.0.0.0 --port 8000 --reload
        fi
        ;;
    
    "frontend")
        print_status "Starting Streamlit Frontend..."
        cd frontend
        
        if port_in_use 8501; then
            print_error "Port 8501 is already in use. Please free the port and try again."
            exit 1
        fi
        
        if ! command_exists streamlit; then
            print_error "Streamlit is not installed. Installing now..."
            pip install streamlit
        fi
        
        streamlit run streamlit_app.py --server.port=8501 --server.address=0.0.0.0
        ;;
    
    "test")
        print_status "Running Tests..."
        if ! command_exists pytest; then
            print_error "pytest is not installed. Installing now..."
            pip install pytest pytest-asyncio
        fi
        
        pytest tests/ -v
        ;;
    
    "install")
        print_status "Installing Dependencies..."
        pip install -r requirements.txt
        
        # Additional development dependencies
        if [ "$ENVIRONMENT" = "development" ]; then
            pip install pytest pytest-asyncio
        fi
        ;;
    
    *)
        echo "Usage: $0 {docker|backend|frontend|test|install}"
        echo "  docker    - Start with Docker Compose"
        echo "  backend   - Start only the backend API"
        echo "  frontend  - Start only the frontend"
        echo "  test      - Run tests"
        echo "  install   - Install dependencies"
        exit 1
        ;;
esac