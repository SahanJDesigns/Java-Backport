#!/bin/bash
# This script runs on the HOST. It starts Docker to run the tests.
set -euo pipefail

echo "=== Starting JDK 17 Tests in Docker for ${COMMIT_SHA:0:7} ==="

# Define the internal test script inside the container
TEST_SCRIPT_PATH_IN_CONTAINER="/tmp/test.sh"
LOCAL_TEST_SCRIPT="${TOOLKIT_DIR}/test.sh"

# Ensure the local test script exists
if [ ! -f "${LOCAL_TEST_SCRIPT}" ]; then
    echo "❌ Error: test.sh not found at ${LOCAL_TEST_SCRIPT}"
    exit 1
fi

# Run the tests in a Docker container
if docker run --rm --dns=8.8.8.8 \
    -v "${PROJECT_DIR}:/repo" \
    -v "${LOCAL_TEST_SCRIPT}:${TEST_SCRIPT_PATH_IN_CONTAINER}" \
    -e "COMMIT_SHA=${COMMIT_SHA}" \
    -e "BUILD_DIR_NAME=${BUILD_DIR_NAME}" \
    -e "TEST_TARGETS=${TEST_TARGETS}" \
    -e "JTREG_HOME=${JTREG_HOME}" \
    -w /repo \
    "${BUILDER_IMAGE_TAG}" \
    bash "${TEST_SCRIPT_PATH_IN_CONTAINER}"
then
    echo "=== Tests passed for ${COMMIT_SHA:0:7} ==="
    exit 0
else
    echo "=== Tests failed for ${COMMIT_SHA:0:7} ==="
    exit 1
fi

