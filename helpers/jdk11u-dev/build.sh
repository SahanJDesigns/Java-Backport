#!/usr/bin/env bash
# This script runs INSIDE the Docker container
set -euo pipefail

echo "=== Building JDK for ${COMMIT_SHA:0:7} (Inside Container) ==="

# The Boot JDK and jtreg are provided by the Docker image's env variables
echo "Using Boot JDK: ${BOOT_JDK}"
echo "Using jtreg: ${JTREG_HOME}"

# Checkout the specific commit
echo "Checking out commit: ${COMMIT_SHA}"
git checkout -f "${COMMIT_SHA}"

# Use a shared build directory to enable incremental builds
export BUILD_DIR_ABS="/repo/build_shared"
echo "--- Using shared build directory for incremental builds: ${BUILD_DIR_ABS} ---"

# Check if we need to configure (only on first build or if configure changed)
NEED_CONFIGURE=false
if [ ! -f "${BUILD_DIR_ABS}/Makefile" ]; then
    echo "--- No existing Makefile found, will configure ---"
    NEED_CONFIGURE=true
    mkdir -p "${BUILD_DIR_ABS}"
fi

# 'cd' into the build directory
cd "${BUILD_DIR_ABS}"

if [ "${NEED_CONFIGURE}" = true ]; then
    echo "--- Configuring build from outside source dir... ---"
    bash ../configure \
        --with-boot-jdk="${BOOT_JDK}" \
        --with-jtreg="${JTREG_HOME}" \
        --enable-ccache \
        --disable-warnings-as-errors \
        --with-debug-level=release \
        --with-native-debug-symbols=none
else
    echo "--- Skipping configure (using existing configuration for incremental build) ---"
fi

# Build the JDK incrementally
echo "--- Running incremental make... (Output will be in ${BUILD_DIR_ABS}) ---"
    
# Run 'make' from inside the build dir.
# Make will automatically detect what needs to be rebuilt
make JOBS="${MAKE_JOBS:-$(nproc)}" images COMPILER_WARNINGS_FATAL=false

echo "=== Build OK ==="