FROM python:3.12-slim

WORKDIR /srv
COPY backend/requirements.txt backend/requirements-ml.txt ./backend/
ARG INSTALL_ML=true
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r backend/requirements.txt \
 && if [ "$INSTALL_ML" = "true" ]; then pip install --no-cache-dir -r backend/requirements-ml.txt; fi
COPY backend/ ./backend/
COPY config/ ./config/
COPY prompts/ ./prompts/
RUN useradd -m -u 10001 appuser && mkdir -p /data/uploads && chown -R appuser:appuser /data/uploads
ENV PYTHONPATH=/srv/backend UPLOAD_ROOT=/data/uploads
EXPOSE 8000
USER appuser
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
