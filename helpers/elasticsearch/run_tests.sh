#!/bin/bash
set -e

echo "=== Running Tests for ${COMMIT_SHA:0:7} ==="
echo "Target: ${TEST_TARGETS}"

# 1. Reconstruct the Docker Image Tag
# Elasticsearch builds its own image per commit.
# The tag format in main.py is: {repo_name}-{build_type}-{short_sha}
# We passed BUILD_TYPE ("fixed" or "buggy") in the env vars.

IMAGE_TAG="elasticsearch-${BUILD_TYPE}-${COMMIT_SHA:0:7}"

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

# 3. Run Tests in Docker
# Create persistent Gradle cache volumes if they don't exist
docker volume create gradle-cache-es 2>/dev/null || true
docker volume create gradle-wrapper-es 2>/dev/null || true

echo "--- Executing: ${GRADLE_CMD} ---"

# Note: The Dockerfile for ES already sets WORKDIR /repo and user 'gradle'
if docker run --rm \
    --dns=8.8.8.8 \
    -u 1000:1000 \
    -v "gradle-cache-es:/home/gradle/.gradle/caches" \
    -v "gradle-wrapper-es:/home/gradle/.gradle/wrapper" \
    -v "${BUILD_DIR}:/repo/build" \
    "${IMAGE_TAG}" \
    bash -c "${GRADLE_CMD}; \
    GRADLE_EXIT_CODE=\$?; \
    mkdir -p /repo/build/all-test-results; \
    find . -name 'TEST-*.xml' -exec cp {} /repo/build/all-test-results/ \;; \
    exit \$GRADLE_EXIT_CODE"; then
    
    echo "✅ Tests Passed"
    exit 0
else
    echo "❌ Tests Failed"
    exit 1
fi