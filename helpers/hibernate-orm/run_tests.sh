#!/bin/bash
set -e

echo "=== Running Tests for ${COMMIT_SHA:0:7} ==="
echo "Target: ${TEST_TARGETS}"

IMAGE_TAG="${IMAGE_TAG_TO_BUILD:-hibernate-orm-${COMMIT_SHA:0:7}}"

if [ "${TEST_TARGETS}" == "ALL" ]; then
    GRADLE_CMD="./gradlew test --rerun-tasks"
elif [ "${TEST_TARGETS}" == "NONE" ]; then
    echo "No relevant source code changes found. Skipping tests."
    exit 0
else
    GRADLE_CMD="./gradlew ${TEST_TARGETS} --rerun-tasks"
fi

DOCKER_CMD="docker"
${DOCKER_CMD} volume create gradle-cache-hibernate 2>/dev/null || true
${DOCKER_CMD} volume create gradle-wrapper-hibernate 2>/dev/null || true

run_gradle_tests() {
    local extra_setup="$1"
    
    # We use -i for info logs to help helpful console parsing if XMLs are missing
    docker run --rm \
    -v "${PROJECT_DIR}:/repo" \
    -v "gradle-cache-hibernate:/home/gradle/.gradle/caches" \
    -v "gradle-wrapper-hibernate:/home/gradle/.gradle/wrapper" \
    -w /repo \
    "${IMAGE_TAG}" \
    bash -c "set -e; \
    ${extra_setup} \
    git config --global --add safe.directory /repo; \
    ${GRADLE_CMD} -i; \
    RET=\$?; \
    echo \"--- Debug: finding build directories ---\"; \
    find /repo -type d -name \"build\" -maxdepth 3; \
    echo \"--- Debug: Listing all XML files ---\"; \
    find /repo -name \"*.xml\"; \
    exit \$RET"
}

echo "--- Executing tests with default JDK ---"
if run_gradle_tests "" > test_output.log 2>&1; then
    cat test_output.log
    echo "✅ Tests Passed"
    exit 0
fi

cat test_output.log

# Check for known JDK version issues
if grep -q "requires at least JDK 25" test_output.log || grep -q "Unsupported class file major version 69" test_output.log; then
    echo "--- Detected JDK 25 requirement. Retrying tests with JDK 25... ---"
    SETUP_JDK25="export JAVA_HOME=/opt/java/jdk-25; export PATH=\$JAVA_HOME/bin:\$PATH;"
    
    if run_gradle_tests "${SETUP_JDK25}" > test_output.log 2>&1; then
        cat test_output.log
        echo "✅ Tests Passed"
        exit 0
    fi
    cat test_output.log
fi

echo "❌ Tests Failed"
exit 1
