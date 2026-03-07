FROM python:3.12-slim

# Set working directory
WORKDIR /sandbox

# Create non-root user for security
RUN useradd -m -s /bin/bash sandbox && \
    chown -R sandbox:sandbox /sandbox

# Copy runner script
COPY runner.py /sandbox/runner.py

# Switch to non-root user
USER sandbox

# Default command runs the runner script
ENTRYPOINT ["python", "/sandbox/runner.py"]
