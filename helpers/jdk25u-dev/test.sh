#!/bin/bash
# This script runs INSIDE the Docker container
set -e

echo "--- Inside Docker: Running tests for ${COMMIT_SHA:0:7} ---"
echo "Target(s): ${TEST_TARGETS}"

# 1. Define Build Directory (use shared build directory)
BUILD_DIR_ABS="/repo/build_shared"

if [ ! -d "${BUILD_DIR_ABS}" ]; then
    echo "❌ Error: Build directory not found at ${BUILD_DIR_ABS}"
    echo "The build must succeed before running tests."
    exit 1
fi

cd "${BUILD_DIR_ABS}"

# 2. Configure Test Targets
if [ "${TEST_TARGETS}" == "ALL" ]; then
    TEST_LIST="tier1"
elif [ "${TEST_TARGETS}" == "NONE" ]; then
    echo "No relevant source code changes found. Skipping tests."
    exit 0
else
    TEST_LIST="${TEST_TARGETS}"
fi

echo "--- Starting Test Execution in ${BUILD_DIR_ABS} ---"

FINAL_EXIT_CODE=0

# 3. Iterate and Run
for TARGET in ${TEST_LIST}; do
    echo "--- Running target: ${TARGET} ---"

    set +e

    # Case 1: jtreg test file (test/*.java)
    if [[ "${TARGET}" == test/*.java ]]; then
        echo "Detected jtreg test file. Running jtreg on individual file."

        JTREG_BIN="${JTREG_HOME}/bin/jtreg"

        if [ ! -x "${JTREG_BIN}" ]; then
            echo "❌ jtreg executable not found at ${JTREG_BIN}"
            FINAL_EXIT_CODE=1
            continue
        fi

        TARGET_ABS="/repo/${TARGET}"

        "${JTREG_BIN}" \
            -verbose:fail,error \
            -jdk:"${BUILD_DIR_ABS}/images/jdk" \
            "${TARGET_ABS}"

        EXIT_CODE=$?

    # Case 2: tier group (tier1, tier2, etc.)
    else
        echo "Detected tier/group test. Using make test."

        make test TEST="${TARGET}" \
             JOBS=$(nproc) \
             JTREG="VERBOSE=fail,error"

        EXIT_CODE=$?
    fi

    set -e

    if [ ${EXIT_CODE} -ne 0 ]; then
        echo "❌ Target ${TARGET} FAILED"
        FINAL_EXIT_CODE=1
    else
        echo "✅ Target ${TARGET} PASSED"
    fi
done

if [ ${FINAL_EXIT_CODE} -eq 0 ]; then
    echo "=== ALL TESTS PASSED ==="
    exit 0
else
    echo "=== SOME TESTS FAILED ==="
    exit 1
fi
