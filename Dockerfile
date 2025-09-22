# Use official Python runtime as a parent image
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Install system dependencies required for PIL and other libraries
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libffi-dev \
    libssl-dev \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file first to leverage Docker cache
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the current directory contents into the container at /app
COPY . .

# Create necessary directories
RUN mkdir -p logs static/images static/templates

# Make ports available (FastAPI and Streamlit)
EXPOSE 8000 8501

# Define environment variable
ENV PYTHONPATH=/app

# Default command (can be overridden)
#CMD ["uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8000"]

#Backend Container to Include Frontend
CMD ["sh", "-c", "uvicorn backend.app:app --host 0.0.0.0 --port 8000 & streamlit run frontend/streamlit_app.py --server.port 8501 --server.address 0.0.0.0 & wait"]

# Copy the run.sh file
#COPY run.sh .

# Make it executable
#RUN chmod +x run.sh

#CMD ./run.sh  # This will use your custom run.sh script


