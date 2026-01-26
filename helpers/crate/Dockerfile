
FROM maven:3.9-eclipse-temurin-23

# Install necessary tools
RUN apt-get update && apt-get install -y \
    git \
    rsync \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /repo

# Copy Maven settings if needed
# RUN mkdir -p /root/.m2

# Set environment variables
ENV MAVEN_OPTS="-Xmx4g -XX:+UseG1GC"

# Default command
CMD ["/bin/bash"]
