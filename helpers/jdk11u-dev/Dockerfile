# Use the official Temurin 11 image, which has a valid JDK on the PATH
FROM eclipse-temurin:11-jdk

# ---- system packages --------------------------------------------------
# This part is still needed and runs as root
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ccache \
    curl git git-lfs make autoconf zip unzip file \
    libfreetype6-dev libcups2-dev libasound2-dev \
    libx11-dev libxext-dev libxrender-dev libxtst-dev libxt-dev \
    libgtk-3-dev && \
    rm -rf /var/lib/apt/lists/*

# ---- jtreg ------------------------------------------------------------
# Download jtreg 7.3.1+1 for JDK 11
RUN mkdir -p /opt/jtreg && \
    curl -L "https://builds.shipilev.net/jtreg/jtreg-7.3.1+1.zip" -o /tmp/jtreg.zip && \
    unzip -q /tmp/jtreg.zip -d /opt/ && \
    rm /tmp/jtreg.zip && \
    chmod +x /opt/jtreg/bin/jtreg /opt/jtreg/bin/jtdiff && \
    printf '#!/bin/sh\nJT_HOME=/opt/jtreg exec /opt/jtreg/bin/jtreg "$@"\n' > /usr/local/bin/jtreg && \
    chmod +x /usr/local/bin/jtreg && \
    jtreg -version

# ---- Boot JDK setup -------------------------------------------------
ENV BOOT_JDK=/opt/java/openjdk
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