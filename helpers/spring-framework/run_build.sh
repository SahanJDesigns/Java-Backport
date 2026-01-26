#!/bin/bash
set -e

echo "--- Building Spring Framework for ${COMMIT_SHA:0:7} ---"

cd "${PROJECT_DIR}"

echo "--- Checking out commit... ---"
git checkout -f ${COMMIT_SHA}
git clean -fd

# Create persistent Gradle cache volumes
docker volume create gradle-cache-spring 2>/dev/null || true
docker volume create gradle-wrapper-spring 2>/dev/null || true

echo "--- Building Docker image with adaptive Java version... ---"

# Detect Gradle version and choose appropriate Java version
JAVA_VERSION=17
if [ -f "gradle/wrapper/gradle-wrapper.properties" ]; then
    GRADLE_URL=$(grep "distributionUrl" gradle/wrapper/gradle-wrapper.properties 2>/dev/null || echo "")
    if [ ! -z "$GRADLE_URL" ]; then
        GRADLE_VER=$(echo $GRADLE_URL | grep -oE '[0-9]+\.[0-9]+' | head -1)
        echo "Detected Gradle version: $GRADLE_VER"
        
        MAJOR=$(echo $GRADLE_VER | cut -d. -f1)
        MINOR=$(echo $GRADLE_VER | cut -d. -f2)
        
        if [ "$MAJOR" -ge 8 ]; then
            JAVA_VERSION=17
        else
            JAVA_VERSION=11
        fi
    fi
fi

echo "Using Java version: $JAVA_VERSION"

# Build the Docker image with detected Java version
docker build --build-arg JAVA_VERSION=${JAVA_VERSION} -t ${IMAGE_TAG} -f ${TOOLKIT_DIR}/Dockerfile ${TOOLKIT_DIR}

echo "--- Running Gradle build (compile only, no tests) ---"

# Fix basic layout before running build (permissions handled by running as root)
docker run --rm \
    -v "${PROJECT_DIR}:/repo" \
    -w /repo \
    ${IMAGE_TAG} \
    bash -c "set -e; \
             rm -rf /repo/build /repo/buildSrc/.gradle 2>/dev/null || true; \
             rm -f /repo/.git/index.lock 2>/dev/null || true; \
             find /repo -type f -name gradlew -exec chmod +x {} + 2>/dev/null || true; \
             mkdir -p /repo/.gradle /repo/build /repo/buildSrc/.gradle; \
             touch /repo/build/build-scan-uri.txt 2>/dev/null || true; \
             chmod -R 755 /repo/build /repo/buildSrc 2>/dev/null || true"

# Run build in Docker with the source code mounted (as root to avoid host FS permission issues)
if docker run --rm \
        -v "${PROJECT_DIR}:/repo" \
        -v "gradle-cache-spring:/home/gradle/.gradle/caches" \
        -v "gradle-wrapper-spring:/home/gradle/.gradle/wrapper" \
        -w /repo \
        ${IMAGE_TAG} \
        bash -c "set -e; \
                         git config --global --add safe.directory /repo; \
                         git reset --hard HEAD; \
                         git clean -fd; \
                         git checkout -f ${COMMIT_SHA}; \
                         export GRADLE_OPTS='-Dorg.gradle.internal.publish.checksums.insecure=true -Dorg.gradle.scan.publish=false'; \
                         ./gradlew build -x test --no-daemon \
                             -Dorg.gradle.jvmargs='-XX:+IgnoreUnrecognizedVMOptions -XX:+UseG1GC -XX:+UseStringDeduplication'"; then
    echo "Success" > "${BUILD_STATUS_FILE}"
else
    echo "Fail" > "${BUILD_STATUS_FILE}"
fi

echo "--- Build complete for ${COMMIT_SHA:0:7} ---"
