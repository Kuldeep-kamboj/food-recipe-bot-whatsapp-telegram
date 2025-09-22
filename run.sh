#!/bin/bash

# Default to local execution
MODE="local"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --docker)
            MODE="docker"
            shift
            ;;
        --local)
            MODE="local"
            shift
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

run_local() {
    echo "Starting Food Recipe Bot locally..."
    
    # Install dependencies if needed
    if [ ! -d "venv" ]; then
        python -m venv venv
        source venv/bin/activate
        pip install -r requirements.txt
    else
        source venv/bin/activate
    fi
    
    # Start both backend and frontend
    echo "Starting backend on http://localhost:8000"
    uvicorn backend.app:app --host 0.0.0.0 --port 8000 --reload &
    
    echo "Starting frontend on http://localhost:8501"
    streamlit run frontend/streamlit_app.py --server.port 8501 &
    
    echo "Application started!"
    echo "Backend: http://localhost:8000"
    echo "Frontend: http://localhost:8501"
    echo "API Docs: http://localhost:8000/docs"
}

run_docker() {
    echo "Starting Food Recipe Bot with Docker..."
    
    # Check if Docker is installed
    if ! command -v docker &> /dev/null; then
        echo "Docker is not installed. Falling back to local mode."
        run_local
        return
    fi
    
    # Check if docker-compose is installed
    if ! command -v docker-compose &> /dev/null; then
        echo "Docker Compose is not installed. Falling back to local mode."
        run_local
        return
    fi
    
    # Build and start with docker-compose
    docker-compose up -d --build
    
    echo "Application started with Docker!"
    echo "Backend: http://localhost:8000"
    echo "Frontend: http://localhost:8501"
    echo "API Docs: http://localhost:8000/docs"
    echo ""
    echo "To view logs: docker-compose logs -f"
    echo "To stop: docker-compose down"
}

# Execute based on mode
case $MODE in
    "docker")
        run_docker
        ;;
    "local")
        run_local
        ;;
    *)
        echo "Invalid mode: $MODE"
        exit 1
        ;;
esac