# Dockerfile
FROM python:3.10

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the code into the container
COPY . .

# Run the Python script
CMD ["python", "bot.py"]