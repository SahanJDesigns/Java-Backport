#!/bin/bash
set -e

echo "--- Building Hibernate ORM for ${COMMIT_SHA:0:7} ---"
echo "DEBUG: TOOLKIT_DIR=${TOOLKIT_DIR}"
echo "DEBUG: PROJECT_DIR=${PROJECT_DIR}"

cd "${PROJECT_DIR}"

echo "--- Checking out commit... ---"
git checkout -f ${COMMIT_SHA}
git clean -fd

# Create persistent Gradle cache volumes
docker volume create gradle-cache-hibernate 2>/dev/null || true
docker volume create gradle-wrapper-hibernate 2>/dev/null || true

echo "--- Building Docker image ---"
# Default to Java 21 for modern Hibernate, but could be adaptive if needed.
# Hibernate 6.x usually requires 11 or 17. 7.x might require 21.
# We'll stick to 21 as safer baseline for new versions.
# Default to Java 21 for modern Hibernate
JAVA_VERSION=21
IMAGE_TAG=${IMAGE_TAG_TO_BUILD:-hibernate-builder:latest}

echo "DEBUG: Image Tag=${IMAGE_TAG}"
docker build --build-arg JAVA_VERSION=${JAVA_VERSION} -t ${IMAGE_TAG} -f ${TOOLKIT_DIR}/Dockerfile ${TOOLKIT_DIR}

echo "--- Running Gradle build (compile only, no tests) ---"

# Fix basic layout 
docker run --rm \
    -v "${PROJECT_DIR}:/repo" \
    -w /repo \
    ${IMAGE_TAG} \
    bash -c "set -e; \
             rm -rf /repo/build /repo/buildSrc/.gradle 2>/dev/null || true; \
             chmod +x gradlew 2>/dev/null || true; \
             mkdir -p /repo/.gradle /repo/build"

# Run build function
run_gradle_build() {
    local extra_setup="$1"
    
    docker run --rm \
        -v "${PROJECT_DIR}:/repo" \
        -v "gradle-cache-hibernate:/home/gradle/.gradle/caches" \
        -v "gradle-wrapper-hibernate:/home/gradle/.gradle/wrapper" \
        -w /repo \
        ${IMAGE_TAG} \
        bash -c "set -e; \
                 ${extra_setup} \
                 git config --global --add safe.directory /repo; \
                 ./gradlew cleanClasses classes testClasses -x test --no-daemon"
}

echo "--- Attempting build with default JDK ---"
if run_gradle_build "" > build_output.log 2>&1; then
    cat build_output.log
    echo "Success" > "${BUILD_STATUS_FILE}"
    echo "--- Build complete for ${COMMIT_SHA:0:7} ---"
    exit 0
fi

cat build_output.log

# Check for known JDK version issues
# "requires at least JDK 25" -> Explicit check in build script
# "Unsupported class file major version 69" -> Running on older JDK, encountered JDK 25 class
if grep -q "requires at least JDK 25" build_output.log || grep -q "Unsupported class file major version 69" build_output.log; then
    echo "--- Detected JDK 25 requirement. Retrying with JDK 25... ---"
    # Set JAVA_HOME and update PATH within the container
    SETUP_JDK25="export JAVA_HOME=/opt/java/jdk-25; export PATH=\$JAVA_HOME/bin:\$PATH;"
    
    if run_gradle_build "${SETUP_JDK25}" > build_output.log 2>&1; then
        cat build_output.log
        echo "Success" > "${BUILD_STATUS_FILE}"
        echo "--- Build complete for ${COMMIT_SHA:0:7} ---"
        exit 0
    fi
    cat build_output.log
fi

echo "Fail" > "${BUILD_STATUS_FILE}"
exit 1
