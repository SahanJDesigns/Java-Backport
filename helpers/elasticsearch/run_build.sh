#!/bin/bash
# This script builds the Docker image and compiles the code.
set -e # Exit on error

echo "--- Building code for ${COMMIT_SHA:0:7} ---"

echo "--- Changing directory to ${PROJECT_DIR} ---"
cd "${PROJECT_DIR}"

echo "--- Checking out commit... ---"
git checkout ${COMMIT_SHA}

# Create persistent Gradle cache volumes if they don't exist
docker volume create gradle-cache-es 2>/dev/null || true
docker volume create gradle-wrapper-es 2>/dev/null || true

echo "--- Building Docker image... ---"
# -f points to the Dockerfile in our toolkit
# . (the context) is the PROJECT_DIR we just cd'd into
docker build -t ${IMAGE_TAG} -f ${TOOLKIT_DIR}/Dockerfile .

echo "--- Setting cache permissions... ---"
docker run --rm -u root \
    -v "gradle-cache-es:/home/gradle/.gradle/caches" \
    -v "gradle-wrapper-es:/home/gradle/.gradle/wrapper" \
    -v "${BUILD_DIR}:/repo/build" \
    ${IMAGE_TAG} \
    chown -R 1000:1000 /home/gradle/.gradle/caches /home/gradle/.gradle/wrapper /repo/build

echo "--- Compiling and preparing for tests... ---"
if docker run --rm \
    --dns=8.8.8.8 \
    -u 1000:1000 \
    -v "gradle-cache-es:/home/gradle/.gradle/caches" \
    -v "gradle-wrapper-es:/home/gradle/.gradle/wrapper" \
    -v "${BUILD_DIR}:/repo/build" \
    ${IMAGE_TAG} \
    ./gradlew classes testClasses -x :benchmarks:classes -x :benchmarks:testClasses -Dbuild.docker=false --continue; then
    echo "Success" > $BUILD_STATUS_FILE
else
    echo "Fail" > $BUILD_STATUS_FILE
fi

echo "--- Build complete for ${COMMIT_SHA:0:7} ---"