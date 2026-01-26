# Use a base image with necessary tools, we will install JDK 24 manually as Boot JDK
FROM eclipse-temurin:23-jdk

# ---- system packages (Install FIRST because we need curl) ----------------
# This part runs as root
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ccache \
    curl git git-lfs make autoconf zip unzip file \
    libfreetype6-dev libcups2-dev libasound2-dev \
    libx11-dev libxext-dev libxrender-dev libxtst-dev libxt-dev \
    libgtk-3-dev && \
    rm -rf /var/lib/apt/lists/*

# ---- Boot JDK setup (JDK 24) ------------------------------------------
# JDK 25 requires Boot JDK 24 or 25
# Using OpenJDK 24 (24.0.2) from Archive
ENV BOOT_JDK=/opt/java/jdk-24
RUN curl -L "https://download.java.net/java/GA/jdk24.0.2/fdc5d0102fe0414db21410ad5834341f/12/GPL/openjdk-24.0.2_linux-x64_bin.tar.gz" -o /tmp/jdk24.tar.gz && \
    mkdir -p /opt/java && \
    tar -xzf /tmp/jdk24.tar.gz -C /opt/java && \
    # The archive extracts to jdk-24.0.2
    mv /opt/java/jdk-24* /opt/java/jdk-24 && \
    rm /tmp/jdk24.tar.gz

# ---- jtreg ------------------------------------------------------------
# Download jtreg 8 (Required for JDK 25)
RUN mkdir -p /opt/jtreg && \
    curl -L "https://builds.shipilev.net/jtreg/jtreg-8.1+1.zip" -o /tmp/jtreg.zip && \
    unzip -q /tmp/jtreg.zip -d /opt/ && \
    rm /tmp/jtreg.zip && \
    chmod +x /opt/jtreg/bin/jtreg /opt/jtreg/bin/jtdiff && \
    printf '#!/bin/sh\nJT_HOME=/opt/jtreg exec /opt/jtreg/bin/jtreg "$@"\n' > /usr/local/bin/jtreg && \
    chmod +x /usr/local/bin/jtreg && \
    jtreg -version

# ---- Boot JDK setup -------------------------------------------------
# We already set BOOT_JDK above, but let's confirm/reset specific env vars if needed
# ENV BOOT_JDK=/opt/java/jdk-24
RUN echo "Boot JDK is at ${BOOT_JDK}" && ${BOOT_JDK}/bin/java -version

# Export JTREG_HOME
ENV JTREG_HOME=/opt/jtreg

# --- Switch to root user to fix all permission errors ---
WORKDIR /repo
# We will run as ROOT to avoid all permission errors

# Add the repo directory as a "safe directory" for Git
RUN git config --global --add safe.directory /repo

# ---- Git LFS setup ----------------------------------------------------
RUN git lfs install --system
