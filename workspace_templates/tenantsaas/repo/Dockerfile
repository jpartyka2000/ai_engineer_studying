# Application image for the tenantsaas exercise.
#
# Dependencies are installed at BUILD time, not at scaffold time. That is what
# keeps exercise start-up around ten seconds instead of two minutes, and it means
# a flaky or unreachable PyPI cannot eat into the user's time box.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# postgresql-client gives the exercise a working `psql` for seed scripts and for
# poking at the database from inside the container.
RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copied and installed before the source, so editing application code does not
# invalidate the dependency layer.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
