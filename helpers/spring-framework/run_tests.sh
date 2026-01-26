#!/bin/bash
set -e

echo "=== Running Tests for ${COMMIT_SHA:0:7} ==="
echo "Target: ${TEST_TARGETS}"

# 1. Reconstruct the Docker Image Tag
IMAGE_TAG="${IMAGE_TAG:-spring-framework-${BUILD_TYPE}-${COMMIT_SHA:0:7}}"

echo "--- Using Docker Image: ${IMAGE_TAG} ---"

# 2. Configure Test Command
if [ "${TEST_TARGETS}" == "ALL" ]; then
    GRADLE_CMD="./gradlew test"
elif [ "${TEST_TARGETS}" == "NONE" ]; then
    echo "No relevant source code changes found. Skipping tests."
    exit 0
else
    GRADLE_CMD="./gradlew ${TEST_TARGETS}"
fi

# Determine if we need sudo for docker
DOCKER_CMD="docker"
if ! docker info > /dev/null 2>&1; then
    if sudo docker info > /dev/null 2>&1; then
        echo "Docker requires sudo. Using 'sudo docker'."
        DOCKER_CMD="sudo docker"
    else
        echo "Warning: Docker command failed and sudo check failed. Continuing with 'docker' but expect errors."
    fi
fi

# 3. Run Tests in Docker
# Create persistent Gradle cache volumes if they don't exist
${DOCKER_CMD} volume create gradle-cache-spring 2>/dev/null || true
${DOCKER_CMD} volume create gradle-wrapper-spring 2>/dev/null || true

echo "--- Executing: ${GRADLE_CMD} ---"

# First, prep the repo as root (handles any permission wrinkles on host FS)
if ${DOCKER_CMD} run --rm \
    -v "${PROJECT_DIR}:/repo" \
    -w /repo \
    "${IMAGE_TAG}" \
    bash -c "set -e; \
    rm -f /repo/.git/index.lock 2>/dev/null || true; \
    chown -R 1000:1000 /repo; \
    git config --global --add safe.directory /repo; \
    git reset --hard HEAD 2>/dev/null || true; \
    git clean -fd 2>/dev/null || true; \
    git checkout -f ${COMMIT_SHA} 2>/dev/null || true"; then
    true
else
    echo "❌ Failed to prepare repo"
    exit 1
fi

# Now run the tests (as root inside container to avoid NTFS permission issues)
if ${DOCKER_CMD} run --rm \
    -v "${PROJECT_DIR}:/repo" \
    -v "gradle-cache-spring:/home/gradle/.gradle/caches" \
    -v "gradle-wrapper-spring:/home/gradle/.gradle/wrapper" \
    -w /repo \
    "${IMAGE_TAG}" \
    bash -c "set -e; \
    export GRADLE_OPTS='-Dorg.gradle.internal.publish.checksums.insecure=true -Dorg.gradle.scan.publish=false'; \
    ${GRADLE_CMD}; \
    GRADLE_EXIT_CODE=\$?; \
    echo '--- Debug: finding test-results dirs ---'; \
    find . -type d -name 'test-results' 2>/dev/null; \
    echo '--- Debug: finding XML files in test-results ---'; \
    find . -path '*/build/test-results/*/*.xml' 2>/dev/null | head -n 20; \
    echo '--- Debug: listing test results ---'; \
    ls -la ./build/ 2>/dev/null | head -20; \
    exit \$GRADLE_EXIT_CODE"; then
    echo "✅ Tests Passed"
    exit 0
else
    echo "❌ Tests Failed"
    exit 1
fi
