FROM python:3.12-slim

# Set working directory
WORKDIR /sandbox

# Data-science libraries available to submitted code.
# Installed as root, before dropping privileges, so the sandbox user cannot
# modify them at run time. Upper bounds guard against a major-version break;
# --no-cache-dir keeps the image from carrying the pip cache.
# These must also be listed in SAFE_MODULES in runner.py, or the sandbox's
# restricted __import__ will still refuse to import them.
RUN pip install --no-cache-dir \
        "numpy>=1.26,<3" \
        "pandas>=2.1,<3"

# Create non-root user for security
RUN useradd -m -s /bin/bash sandbox && \
    chown -R sandbox:sandbox /sandbox

# Copy runner script
COPY runner.py /sandbox/runner.py

# Switch to non-root user
USER sandbox

# Default command runs the runner script
ENTRYPOINT ["python", "/sandbox/runner.py"]
