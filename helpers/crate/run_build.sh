#!/bin/bash
# This script builds the Docker image and compiles the code.
set -e # Exit on error

echo "--- Building code for ${COMMIT_SHA:0:7} ---"

echo "--- Changing directory to ${PROJECT_DIR} ---"
cd "${PROJECT_DIR}"

echo "--- Checking out commit... ---"
git checkout -f ${COMMIT_SHA}
git clean -fd

# Determine Docker command (with or without sudo)
DOCKER_CMD="docker"
if ! docker info > /dev/null 2>&1; then
    if sudo docker info > /dev/null 2>&1; then
        echo "Docker requires sudo. Using 'sudo docker'."
        DOCKER_CMD="sudo docker"
    else
        echo "Warning: Docker command failed. Continuing with 'docker' but expect errors."
    fi
fi

# Create persistent Maven cache volume
${DOCKER_CMD} volume create maven-cache-crate 2>/dev/null || true

echo "--- Building Docker image... ---"
${DOCKER_CMD} build -t ${IMAGE_TAG} -f ${TOOLKIT_DIR}/Dockerfile .

echo "--- Setting cache permissions... ---"
${DOCKER_CMD} run --rm -u root \
    -v "maven-cache-crate:/root/.m2" \
    -v "${BUILD_DIR}:/repo/build_outputs/build" \
    ${IMAGE_TAG} \
    chown -R root:root /root/.m2

echo "--- Building with Maven... ---"
# Build and install to local repo, skip tests
if ${DOCKER_CMD} run --rm \
    --dns=8.8.8.8 \
    -v "maven-cache-crate:/root/.m2" \
    -v "${BUILD_DIR}:/repo/build_outputs/build" \
    -v "${PROJECT_DIR}:/repo" \
    -w /repo \
    ${IMAGE_TAG} \
    bash -c "git config --global --add safe.directory /repo && mvn clean install -DskipTests -T 1C"; then
    echo "Success" > $BUILD_STATUS_FILE
else
    echo "Fail" > $BUILD_STATUS_FILE
fi

echo "--- Build complete for ${COMMIT_SHA:0:7} ---"