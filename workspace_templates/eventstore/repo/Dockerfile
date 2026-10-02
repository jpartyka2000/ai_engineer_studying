# Application image for the eventstore exercise.
#
# Dependencies are installed at BUILD time, not at scaffold time. That is what keeps
# exercise start-up around ten seconds instead of two minutes, and it means a flaky or
# unreachable PyPI cannot eat into the time box.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Copied and installed before the source, so editing application code does not
# invalidate the dependency layer.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
# Editable, because /app is bind-mounted over by compose: a non-editable install would
# leave the container running the code as it was at build time while you edit the copy
# on disk and wonder why nothing changes.
RUN pip install --no-cache-dir --no-deps -e .

EXPOSE 8000
CMD ["uvicorn", "eventstore.api:app", "--host", "0.0.0.0", "--port", "8000"]
