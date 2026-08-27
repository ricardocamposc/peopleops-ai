FROM python:3.11-slim
WORKDIR /app
ENV PYTHONPATH=/app/src
COPY pyproject.toml ./
RUN pip install --no-cache-dir poetry && poetry config virtualenvs.create false && poetry install --no-root
COPY src ./src
EXPOSE 8001
CMD ["uvicorn", "reference_mcp_server.main:app", "--host", "0.0.0.0", "--port", "8001"]
