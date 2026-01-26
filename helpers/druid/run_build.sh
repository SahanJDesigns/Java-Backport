#!/bin/bash
# Optimized Druid build script with permission fix
set -euo pipefail

echo "=== Building Druid for commit ${COMMIT_SHA:0:7} ==="

# Initialize build exit code
BUILD_EXIT_CODE=0

cd "${PROJECT_DIR}"

# FIX: Use Docker as root to forcefully clean and fix permissions
echo "=== Cleaning Docker-created files and fixing permissions ==="
docker run --rm \
    -v "${PROJECT_DIR}:/repo" \
    -w /repo \
    --user root \
    ${BUILDER_IMAGE_TAG} \
    bash -c "git config --global --add safe.directory /repo && git clean -fdx && chown -R $(id -u):$(id -g) /repo" || true

# Now checkout can succeed
echo "=== Checking out commit ${COMMIT_SHA} ==="
git checkout -f ${COMMIT_SHA}

# Create Maven cache volume (reuse across builds)
docker volume create maven-repo 2>/dev/null || true

echo "=== Running standard Maven build ==="

# Run Maven build
# Reverted to standard install as requested
docker run --rm \
    -v "${PROJECT_DIR}:/repo" \
    -v "maven-repo:/root/.m2/repository" \
    -w /repo \
    ${BUILDER_IMAGE_TAG} \
    bash -c "sed -i '/<artifactId>frontend-maven-plugin<\/artifactId>/,/<\/configuration>/ s/<configuration>/<configuration><skip>true<\/skip>/' web-console/pom.xml && mvn clean install -DskipTests -Dweb.console.skip=true -Dmaven.javadoc.skip=true -Dcheckstyle.skip=true -Dpmd.skip=true -Dforbiddenapis.skip=true -Denforcer.skip=true -Drat.skip=true -T 1C -pl '!:distribution'" \
    || BUILD_EXIT_CODE=$?

# Save build status
if [ ${BUILD_EXIT_CODE} -eq 0 ]; then
    echo "Success" > "${BUILD_STATUS_FILE}"
    echo "✅ Build succeeded for ${COMMIT_SHA:0:7}"
else
    echo "Fail" > "${BUILD_STATUS_FILE}"
    echo "❌ Build failed for ${COMMIT_SHA:0:7}"
fi

echo "=== Build finished for ${COMMIT_SHA:0:7} ==="