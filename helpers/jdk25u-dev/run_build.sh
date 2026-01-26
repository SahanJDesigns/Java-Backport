#!/bin/bash
# This script runs the JDK build inside our pre-built Docker container.
set -euo pipefail

echo "=== Starting JDK Build in Docker for ${COMMIT_SHA:0:7} ==="

# Define the build script to run inside the container
# We mount it from the toolkit
BUILD_SCRIPT_PATH_IN_CONTAINER="/tmp/build.sh"
LOCAL_BUILD_SCRIPT="${TOOLKIT_DIR}/build.sh"

# Create a persistent ccache directory on the host to speed up compilation
# Use specific ccache for jdk25
CCACHE_DIR="${PROJECT_DIR}/../.ccache_jdk25"
mkdir -p "${CCACHE_DIR}"

# Run the build in a container
# - Mount the project repo to /repo
# - Mount the build script to /tmp/build.sh
# - Mount persistent ccache directory
# - Pass in the COMMIT_SHA
# - Set the working directory to /repo
# - Use the pre-built builder image
if docker run --rm --dns=8.8.8.8 \
    -v "${PROJECT_DIR}:/repo" \
    -v "${LOCAL_BUILD_SCRIPT}:${BUILD_SCRIPT_PATH_IN_CONTAINER}" \
    -v "${CCACHE_DIR}:/root/.ccache" \
    -e "COMMIT_SHA=${COMMIT_SHA}" \
    -e "BUILD_DIR_NAME=${BUILD_DIR_NAME}" \
    -e "BOOT_JDK=${BOOT_JDK}" \
    -e "JTREG_HOME=${JTREG_HOME}" \
    -e "CCACHE_DIR=/root/.ccache" \
    -w /repo \
    "${BUILDER_IMAGE_TAG}" \
    bash "${BUILD_SCRIPT_PATH_IN_CONTAINER}"
then
    echo "Success" > "${BUILD_STATUS_FILE}"
else
    echo "Fail" > "${BUILD_STATUS_FILE}"
fi

echo "=== Build finished for ${COMMIT_SHA:0:7} ==="
