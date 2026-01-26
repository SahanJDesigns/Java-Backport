#!/bin/bash
set -e # Exit on error

echo "--- Building code for ${COMMIT_SHA:0:7} ---"

# 1. Checkout commit
echo "--- Changing directory to ${PROJECT_DIR} ---"
cd "${PROJECT_DIR}"

echo "--- Checking out commit... ---"
git checkout -f ${COMMIT_SHA}

# 2. Build Docker image
echo "--- Building Docker image... ---"
docker build -t ${BUILDER_IMAGE_TAG} -f ${TOOLKIT_DIR}/Dockerfile .

# 3. Run Build
# We mount the repo and the maven cache
# We use 'mvn clean install -DskipTests' to build everything needed for tests
# We might need to skip frontend builds if they are flaky, similar to Druid
echo "--- Running Maven Build... ---"

# Create volume for maven repo if not exists
docker volume create maven-repo 2>/dev/null || true

# Run build
# We add -Dskip.npm -Dskip.installnodenpm just in case Graylog uses frontend-maven-plugin too
docker run --rm \
    -v "${PROJECT_DIR}:/repo" \
    -v "maven-repo:/root/.m2/repository" \
    -w /repo \
    ${BUILDER_IMAGE_TAG} \
    bash -c "mvn clean install -DskipTests -Dskip.yarn -Dskip.npm -Dskip.installnodenpm -Dmaven.antrun.skip=true -Dmaven.javadoc.skip=true -Dcheckstyle.skip=true -Dpmd.skip=true -Dforbiddenapis.skip=true -Denforcer.skip=true -Drat.skip=true -T 1C" \
    || BUILD_EXIT_CODE=$?

# Save build status
if [ -z "$BUILD_EXIT_CODE" ] || [ "$BUILD_EXIT_CODE" -eq 0 ]; then
    echo "Success" > $BUILD_STATUS_FILE
else
    echo "Fail" > $BUILD_STATUS_FILE
fi

echo "--- Build complete for ${COMMIT_SHA:0:7} ---"
