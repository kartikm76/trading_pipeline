# 1. Use the EMR 7.11.0 base (must match EMR application version)
FROM public.ecr.aws/emr-serverless/spark/emr-7.11.0:latest

USER root

# 2. Install Python 3.12 (Amazon Linux 2023 package)
RUN dnf install -y python3.12 python3.12-pip && dnf clean all

# 3. Get uv for fast, reliable dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# 4. Sync dependencies from pyproject.toml
WORKDIR /app
COPY pyproject.toml uv.lock* ./

# --python /usr/bin/python3.12: Forces uv to use the new version
# --system: Installs libraries into the image's python site-packages
RUN uv pip install --system --python /usr/bin/python3.12 --no-cache -r pyproject.toml
COPY src/ /app/src/
COPY config.yaml /app/config.yaml

# 5. Tell Spark to use Python 3.12 on the executors
ENV PYTHONPATH="/app/src:${PYTHONPATH}"
ENV PYSPARK_PYTHON=/usr/bin/python3.12
ENV PYSPARK_DRIVER_PYTHON=/usr/bin/python3.12

# 6. Set user back to hadoop
USER hadoop:hadoop
WORKDIR /home/hadoop