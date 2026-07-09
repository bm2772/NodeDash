# NodeDash backend (API). Frontend is deployed separately to Vercel.
FROM python:3.12-slim

WORKDIR /app

# deps first for layer caching
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# app code + the questionnaire files the backend reads at runtime
COPY backend/ backend/
COPY questionnaire/ questionnaire/

WORKDIR /app/backend
ENV PORT=8080
EXPOSE 8080

# App Platform / most hosts inject $PORT; default to 8080 locally
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
