#!/bin/bash
set -e

# grpc-java build script
# Mounts: /repo (project dir), /home/gradle/.gradle (cache)

echo "--- Building grpc-java for ${COMMIT_SHA:0:7} ---"

# Fix ownership if mounted as root
chown -R gradle:gradle /repo

# Run as gradle user
# We use 'assemble' to build everything, or 'install' to put artifacts in local repo
# Skipping tests during build phase
su gradle -c "./gradlew clean assemble -x test --no-daemon"

# Check if build succeeded (gradlew exits non-zero on failure, but we check artifact existence or status file)
if [ $? -eq 0 ]; then
    echo "Success" > "${BUILD_STATUS_FILE}"
    echo "--- Build Successful ---"
else
    echo "Fail" > "${BUILD_STATUS_FILE}"
    echo "--- Build Failed ---"
fi
