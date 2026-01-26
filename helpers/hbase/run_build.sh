#!/bin/bash
# This script compiles HBase code using pre-built Docker image (Maven project)
set -e # Exit on error

echo "--- Building HBase for commit ${COMMIT_SHA:0:7} ---"

echo "--- Changing directory to ${PROJECT_DIR} ---"
cd "${PROJECT_DIR}"

echo "--- Checking out commit... ---"
git checkout -f ${COMMIT_SHA}

# Create persistent Maven cache volume (reuse across builds)
docker volume create maven-cache-hbase 2>/dev/null || true

echo "--- Running Maven build (compile only, no tests) ---"

# Build without tests, skip documentation and code quality checks
BUILD_COMMAND="mvn clean install -DskipTests \
  -Dmaven.javadoc.skip=true \
  -Dcheckstyle.skip=true \
  -Dfindbugs.skip=true \
  -Dspotbugs.skip=true \
  -Denforcer.skip=true"

if docker run --rm \
    --dns=8.8.8.8 \
    -v "${PROJECT_DIR}:/repo" \
    -v "maven-cache-hbase:/root/.m2" \
    -w /repo \
    ${BUILDER_IMAGE_TAG} \
    bash -c "rm -rf /root/.m2/repository/org/apache/hbase && ${BUILD_COMMAND}"; then
    echo "Success" > "${BUILD_STATUS_FILE}"
else
    echo "Fail" > "${BUILD_STATUS_FILE}"
fi

echo "--- Build complete for ${COMMIT_SHA:0:7} ---"
