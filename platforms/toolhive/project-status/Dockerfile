# Build from the repo root: docker build -f platforms/toolhive/project-status/Dockerfile -t project-status:<ver> .
FROM python:3.12-slim
RUN pip install --no-cache-dir "mcp[cli]>=1.2,<2" uvicorn httpx pydantic starlette \
 && useradd --system --uid 10001 app
WORKDIR /app
COPY src/project_status /app/project_status
ENV PYTHONPATH=/app PYTHONUNBUFFERED=1
USER 10001
EXPOSE 8080
CMD ["python", "-m", "project_status.toolhive_main"]
