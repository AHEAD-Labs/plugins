FROM python:3.12-slim
RUN pip install --no-cache-dir starlette uvicorn httpx "pyjwt[crypto]" azure-storage-blob azure-identity
WORKDIR /app
COPY src/platform_gateway/__init__.py src/platform_gateway/entra.py src/platform_gateway/revocations.py /app/platform_gateway/
COPY platforms/azure/gateway/app.py /app/gateway_app.py
ENV PYTHONPATH=/app
EXPOSE 8080
CMD ["uvicorn", "gateway_app:app", "--host", "0.0.0.0", "--port", "8080"]
