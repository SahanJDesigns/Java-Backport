#!/bin/bash
set -e

echo "=== Running Tests for ${COMMIT_SHA:0:7} ==="
echo "Target: ${TEST_TARGETS}"

# Fix ownership
chown -R gradle:gradle /repo

if [ "${TEST_TARGETS}" == "ALL" ]; then
    GRADLE_CMD="./gradlew test --no-daemon"
elif [ "${TEST_TARGETS}" == "NONE" ]; then
    echo "No relevant tests. Skipping."
    exit 0
else
    # TEST_TARGETS should be in Gradle format: --tests "ClassName" or "ClassName.methodName"
    # The get_test_targets.py should produce this format
    GRADLE_CMD="./gradlew test ${TEST_TARGETS} --no-daemon"
fi

echo "--- Executing: ${GRADLE_CMD} ---"

su gradle -c "${GRADLE_CMD}"

EXIT_CODE=$?

# Copy results (xml files) to a location accessible by host (mapped volume)
# Assumes run_tests.py maps a volume or directory for output
# We might need to copy specific xmls if they are deep in submodules

echo "--- Tests finished with exit code ${EXIT_CODE} ---"
exit ${EXIT_CODE}
