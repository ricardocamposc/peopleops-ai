FROM python:3.11-slim
WORKDIR /app
ENV PYTHONPATH=/app/src
COPY pyproject.toml ./
RUN pip install --no-cache-dir poetry && poetry config virtualenvs.create false && poetry install --no-root
COPY src ./src
COPY alembic.ini ./alembic.ini
COPY alembic ./alembic
EXPOSE 8000
CMD ["uvicorn", "peopleops_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
