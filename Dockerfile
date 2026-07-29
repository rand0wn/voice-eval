FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY scenarios ./scenarios
RUN pip install --no-cache-dir .
ENV VOICE_EVAL_SCENARIO_DIR=/app/scenarios
EXPOSE 8000
CMD ["uvicorn", "voice_agent_eval_lab.api:app", "--host", "0.0.0.0", "--port", "8000"]
