#!/usr/bin/env bash
# build_lambda.sh — build and upload the pubHealthLLM Lambda ZIP
#
# Usage:
#   export LAMBDA_ARTIFACT_BUCKET=<bucket-name>  # from: terraform -chdir=terraform/6_backend output -raw artifact_bucket
#   bash scripts/build_lambda.sh
#
# Produces: pubhealth-backend.zip uploaded to s3://$LAMBDA_ARTIFACT_BUCKET/pubhealth-backend.zip
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKEND_DIR="$REPO_ROOT/backend"
BUILD_DIR="$(mktemp -d)"
trap 'rm -rf "$BUILD_DIR"' EXIT
ZIP_NAME="pubhealth-backend.zip"
ZIP_PATH="$REPO_ROOT/$ZIP_NAME"

echo "=== Build dir: $BUILD_DIR ==="

# 1. Install lean dependencies targeting Lambda's Linux runtime
echo "=== Installing lean dependencies ==="
python3 -m pip install \
  --quiet \
  --target "$BUILD_DIR" \
  --platform manylinux2014_x86_64 \
  --python-version 3.12 \
  --implementation cp \
  --only-binary=:all: \
  --upgrade \
  -r "$BACKEND_DIR/requirements-lambda.txt"

# 2. Copy application source
echo "=== Copying source ==="
cp -r "$BACKEND_DIR/pubhealth_llm" "$BUILD_DIR/"
cp "$BACKEND_DIR/server.py"         "$BUILD_DIR/"
cp "$BACKEND_DIR/lambda_handler.py" "$BUILD_DIR/"

# 3. Check unzipped size before zipping
UNZIPPED_MB=$(du -sm "$BUILD_DIR" | cut -f1)
echo "=== Unzipped size: ${UNZIPPED_MB} MB ==="
if [ "$UNZIPPED_MB" -gt 250 ]; then
  echo "ERROR: Unzipped package (${UNZIPPED_MB} MB) exceeds 250 MB Lambda limit."
  echo "Consider switching to a container image deployment."
  rm -rf "$BUILD_DIR"
  exit 1
fi

# 4. Build ZIP
echo "=== Building ZIP ==="
rm -f "$ZIP_PATH"
# NOTE: do NOT exclude *.dist-info/* — opentelemetry (a pydantic-ai dep) uses
# entry_points() at import time to discover its context implementation. Stripping
# dist-info removes those registrations and causes StopIteration on Lambda init.
(cd "$BUILD_DIR" && zip -r9q "$ZIP_PATH" . \
  --exclude "*.pyc" \
  --exclude "*/__pycache__/*" \
  --exclude "*.egg-info/*")

ZIP_MB=$(du -sm "$ZIP_PATH" | cut -f1)
echo "=== ZIP size: ${ZIP_MB} MB (compressed) ==="

# 5. Upload to S3
BUCKET="${LAMBDA_ARTIFACT_BUCKET:?Set LAMBDA_ARTIFACT_BUCKET to the Terraform output: artifact_bucket}"
echo "=== Uploading to s3://$BUCKET/$ZIP_NAME ==="
aws s3 cp "$ZIP_PATH" "s3://$BUCKET/$ZIP_NAME"

rm -rf "$BUILD_DIR"
echo "=== Done: s3://$BUCKET/$ZIP_NAME ==="
