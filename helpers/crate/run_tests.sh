#!/bin/bash
set -e

echo "=== Running Tests for ${COMMIT_SHA:0:7} ==="
echo "Target: ${TEST_TARGETS}"

IMAGE_TAG="${IMAGE_TAG:-crate-${BUILD_TYPE}-${COMMIT_SHA:0:7}}"

echo "--- Using Docker Image: ${IMAGE_TAG} ---"

# Configure Test Command
if [ "${TEST_TARGETS}" == "ALL" ]; then
    MVN_CMD="mvn test -T 1C"
elif [ "${TEST_TARGETS}" == "NONE" ]; then
    echo "No relevant source code changes found. Skipping tests."
    exit 0
else
    # TEST_TARGETS is a space-separated list of "module:class"
    # Example: sql:io.crate.FooTest
    
    MODULES=""
    TESTS=""
    
    # Split by space
    for target in ${TEST_TARGETS}; do
        # Split by colon
        mod="${target%%:*}"
        cls="${target#*:}"
        
        # Append to lists (comma separated)
        if [ -n "$mod" ]; then
            if [ -z "$MODULES" ]; then
                MODULES="$mod"
            else
                # Avoid duplicates
                if [[ ",$MODULES," != *",$mod,"* ]]; then
                    MODULES="$MODULES,$mod"
                fi
            fi
        fi
        
        if [ -z "$TESTS" ]; then
            TESTS="$cls"
        else
            TESTS="$TESTS,$cls"
        fi
    done
    
    # If modules found, use -pl
    if [ -n "$MODULES" ]; then
        MVN_CMD="mvn -pl ${MODULES} -Dtest=${TESTS} test"
    else
        MVN_CMD="mvn -Dtest=${TESTS} test"
    fi
fi

DOCKER_CMD="docker"
if ! docker info > /dev/null 2>&1; then
    if sudo docker info > /dev/null 2>&1; then
        echo "Docker requires sudo. Using 'sudo docker'."
        DOCKER_CMD="sudo docker"
    else
        echo "Warning: Docker command failed. Continuing with 'docker' but expect errors."
    fi
fi

${DOCKER_CMD} volume create maven-cache-crate 2>/dev/null || true

echo "--- Executing: ${MVN_CMD} ---"

if ${DOCKER_CMD} run --rm \
    --dns=8.8.8.8 \
    -v "maven-cache-crate:/root/.m2" \
    -v "${BUILD_DIR}:/repo/build_outputs" \
    -v "${PROJECT_DIR}:/repo" \
    -w /repo \
    "${IMAGE_TAG}" \
    bash -c "git config --global --add safe.directory /repo && ${MVN_CMD}; \
    MVN_EXIT_CODE=\$?; \
    echo '--- Copying test reports with rsync ---'; \
    mkdir -p /repo/build_outputs/build; \
    rsync -a --include='*/' --include='*.xml' --exclude='*' --include='**/target/surefire-reports/**' /repo/ /repo/build_outputs/build/ || echo 'Rsync failed'; \
    echo '--- Test results copied ---'; \
    find /repo/build_outputs -name '*.xml' | head -20; \
    exit \$MVN_EXIT_CODE"; then
    
    echo "✅ Tests Passed"
    exit 0
else
    echo "❌ Tests Failed"
    exit 1
fi