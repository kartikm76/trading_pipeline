#!/bin/bash
set -e # Exit on error

# Capture the first argument, default to 'false'
IS_BOOTSTRAP=${1:-false}

# --- CONFIGURATION ---
S3_BUCKET="trading-pipeline" # Update to your actual bucket
DIST_DIR="./dist"
LAST_HASH_FILE=".last_pyproject_hash"
mkdir -p $DIST_DIR

echo "--- 🚀 Starting High-Hygiene Deployment ---"

# --- 1. SOURCE SHARED CONFIG ---
if [ -f "infrastructure/.spark_conf" ]; then
    source infrastructure/.spark_conf
else
    echo "⚠️ Warning: .spark_conf not found. Using default parameters."
fi

# --- 2. CONDITIONAL DEPENDENCY PACKAGING (The 'uv' Way) ---
# Calculate hash of pyproject.toml to detect changes
PYPROJECT_HASH=$(shasum pyproject.toml | awk '{ print $1 }')

if [ ! -f "$DIST_DIR/pyspark_deps.tar.gz" ] || [ ! -f "$LAST_HASH_FILE" ] || [ "$PYPROJECT_HASH" != "$(cat $LAST_HASH_FILE)" ]; then
    echo "📦 Change detected in pyproject.toml or archive missing. Rebuilding with Docker..."

    # We use a Dockerized uv export to ensure the environment is built for EMR (Amazon Linux 2023 / amd64)
    docker run --rm -v $(pwd):/app -w /app --platform linux/amd64 ghcr.io/astral-sh/uv:latest /bin/bash -c "
      apt-get update && apt-get install -y python3-venv tar gzip
      uv export --format requirements-txt > /tmp/reqs.txt
      python3 -m venv venv_emr
      source venv_emr/bin/activate
      pip install --upgrade pip
      pip install -r /tmp/reqs.txt venv-pack
      venv-pack -o /app/dist/pyspark_deps.tar.gz -f
      rm -rf venv_emr
    "
    echo "$PYPROJECT_HASH" > "$LAST_HASH_FILE"
    echo "✅ Dependencies packaged successfully."
else
    echo "⚡ No changes in pyproject.toml. Skipping dependency build."
fi

# --- 3. SOURCE PACKAGING ---
echo "📂 Packaging source code..."
zip -r $DIST_DIR/src.zip src/ -x "*.pyc" "__pycache__/*" ".DS_Store"

# --- 4. S3 SYNC ---
echo "☁️ Syncing artifacts to S3: $S3_BUCKET"
aws s3 cp $DIST_DIR/pyspark_deps.tar.gz s3://$S3_BUCKET/artifacts/
aws s3 cp $DIST_DIR/src.zip s3://$S3_BUCKET/artifacts/
aws s3 cp config.yaml s3://$S3_BUCKET/artifacts/
aws s3 cp src/main.py s3://$S3_BUCKET/artifacts/

echo "--- ✅ Deployment Complete ---"