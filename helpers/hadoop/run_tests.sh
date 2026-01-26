#!/bin/bash
set -e

echo "=== Running Tests for ${COMMIT_SHA:0:7} ==="
echo "Target: ${TEST_TARGETS}"

# 1. Configure Test Command
if [ "${TEST_TARGETS}" == "ALL" ]; then
    echo "--- Running ALL tests (excluding blacklisted modules) ---"
    MAVEN_ARGS="-pl '!hadoop-yarn-project/hadoop-yarn/hadoop-yarn-applications/hadoop-yarn-applications-catalog/hadoop-yarn-applications-catalog-webapp,!hadoop-yarn-project/hadoop-yarn/hadoop-yarn-applications/hadoop-yarn-applications-catalog/hadoop-yarn-applications-catalog-docker'"
elif [ "${TEST_TARGETS}" == "NONE" ]; then
    echo "No relevant source code changes found. Skipping tests."
    exit 0
else
    # Check if we have granular targets (contain ':')
    if [[ "${TEST_TARGETS}" == *":"* ]]; then
        echo "--- Granular Test Mode: Running specific test classes ---"
        
        MODULES=""
        CLASSES=""
        
        # Parse targets
        for target in ${TEST_TARGETS}; do
            if [[ "$target" == *":"* ]]; then
                MOD="${target%%:*}"
                CLS="${target#*:}"
                
                # Add to comma-separated lists
                if [ -z "$MODULES" ]; then
                    MODULES="$MOD"
                else
                    # Check if module already in list
                    if [[ ",$MODULES," != *",$MOD,"* ]]; then
                        MODULES="$MODULES,$MOD"
                    fi
                fi
                
                if [ -z "$CLASSES" ]; then
                    CLASSES="$CLS"
                else
                    CLASSES="$CLASSES,$CLS"
                fi
            fi
        done
        
        if [ -z "$CLASSES" ]; then
            echo "Error: No valid test classes found"
            exit 1
        fi
        
        echo "Modules: $MODULES"
        echo "Test Classes: $CLASSES"
        echo "Number of test classes: $(echo $CLASSES | tr ',' '\n' | wc -l)"
        
        # Use -Dtest to run specific tests, -am to build dependencies
        MAVEN_ARGS="-pl ${MODULES} -Dtest=${CLASSES} -am -DfailIfNoTests=false"
    else
        echo "--- Module Test Mode: Running all tests in affected modules ---"
        
        # Convert space-separated to comma-separated
        COMMA_TARGETS=$(echo "${TEST_TARGETS}" | tr ' ' ',')
        
        echo "Affected Modules: $COMMA_TARGETS"
        
        # Run all tests in specified modules, build dependencies
        MAVEN_ARGS="-pl ${COMMA_TARGETS} -am"
    fi
fi

echo "--- Starting Test Execution ---"
echo "--- Maven Args: ${MAVEN_ARGS} ---"

# 2. Create Maven cache volume
docker volume create maven-cache 2>/dev/null || true

# 3. Run Tests in Docker
if docker run --rm \
    --dns=8.8.8.8 \
    -v "${BUILD_DIR}:/repo" \
    -v "maven-cache:/root/.m2" \
    -w /repo \
    "${IMAGE_TAG}" \
    bash -c "set -e; \
             echo 'Maven version:'; mvn --version; \
             echo 'Running: mvn test ${MAVEN_ARGS}'; \
             mvn test ${MAVEN_ARGS} \
                 -DfailIfNoTests=false \
                 -Dmaven.javadoc.skip=true \
                 -Drat.skip=true \
                 -Dcheckstyle.skip=true \
                 -Denforcer.skip=true; \
             MVN_EXIT_CODE=\$?; \
             echo 'Collecting test results...'; \
             mkdir -p /repo/all-test-results; \
             find . -path '*/target/surefire-reports/TEST-*.xml' -exec cp {} /repo/all-test-results/ \; 2>/dev/null || true; \
             echo \"Found \$(ls /repo/all-test-results/*.xml 2>/dev/null | wc -l) test result files\"; \
             exit \$MVN_EXIT_CODE"; then
    
    echo "✅ Tests Passed"
    exit 0
else
    echo "❌ Tests Failed"
    exit 1
fi