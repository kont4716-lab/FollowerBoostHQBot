FROM mcr.microsoft.com/playwright/python:v1.48.0-jammy

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# تثبيت متصفحات Playwright (احتياطي)
RUN playwright install chromium

CMD gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --timeout 120
