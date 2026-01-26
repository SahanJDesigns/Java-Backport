ARG JAVA_VERSION=17
FROM eclipse-temurin:${JAVA_VERSION}-jdk-jammy

# Install basic tools and C++ build tools (often needed for grpc protoc compilation if not pre-downloaded)
RUN apt-get update && apt-get install -y \
    git \
    python3 \
    build-essential \
    autoconf \
    libtool \
    pkg-config \
    cmake \
    && rm -rf /var/lib/apt/lists/*

# Create a non-root user 'gradle'
RUN groupadd --gid 1000 gradle && \
    useradd --uid 1000 --gid 1000 --shell /bin/bash --create-home gradle

# Create the global .gradle directory
RUN mkdir -p /home/gradle/.gradle && \
    chown -R gradle:gradle /home/gradle/.gradle

# Configure Gradle to avoid daemon issues in Docker
RUN echo "org.gradle.daemon=false" >> /home/gradle/.gradle/gradle.properties && \
    echo "org.gradle.console=plain" >> /home/gradle/.gradle/gradle.properties && \
    chown gradle:gradle /home/gradle/.gradle/gradle.properties

# Set up working directory
RUN mkdir -p /repo && chown gradle:gradle /repo
WORKDIR /repo
