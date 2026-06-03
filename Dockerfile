FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for Pillow
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    libjpeg-dev \
    zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python packages
COPY FoodStore/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the entire application
COPY FoodStore/ .

# Collect static files
RUN python manage.py collectstatic --noinput

# Run migrations and start server
CMD python manage.py migrate --noinput && gunicorn foodstore.wsgi:application
