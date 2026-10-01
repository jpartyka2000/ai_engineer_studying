# Image for the etlduck exercise.
#
# There is no database server here. DuckDB is a library: the whole warehouse is one file
# under warehouse/, which is why this stack has a single service and starts in seconds.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
# Editable so an edit in src/ takes effect without a rebuild, which matters because the
# workspace is bind-mounted over /app.
RUN pip install --no-cache-dir -e .

CMD ["sleep", "infinity"]
