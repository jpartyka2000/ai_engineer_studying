# Image for the edakit exercise.
#
# The library itself has no runtime dependencies, so this is thin. It exists so the
# suite runs in exactly the same interpreter the grading harness uses, and so
# `pip install .` is exercised the way a consumer would do it.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
# Editable so a change in src/ takes effect without a rebuild, which matters because
# the workspace is bind-mounted.
RUN pip install --no-cache-dir -e .

CMD ["sleep", "infinity"]
