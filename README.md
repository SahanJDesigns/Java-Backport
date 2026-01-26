# JavaBackports: A Dataset for Benchmarking Automated Backporting in Java

[![Dataset](https://img.shields.io/badge/dataset-474%20backports-blue.svg)](#-dataset-overview)
[![Projects](https://img.shields.io/badge/projects-12%20Java%20repos-green.svg)](#-included-projects)

## Dataset Overview

The JavaBackports dataset contains **474 validated backport instances** spanning across major Java projects. Each backport represents a real-world scenario where a patch from a main development branch was adapted and applied to a long-term support or stable release branch.

### Dataset Schema

Each CSV file in the `dataset/` directory contains the following columns:

| Column | Description |
|--------|-------------|
| `Project` | Name of the source project (e.g., "crate", "druid", "jdk17u-dev") |
| `Original Version` | Source branch/version where the original patch was applied (e.g., "trunk", "master") |
| `Original Commit` | SHA hash of the original commit in the source branch |
| `Backport Version` | Target branch/version where the backport was applied (e.g., "3.6", "29.0.1") |
| `Backport Commit` | SHA hash of the backported commit in the target branch (the **FIXED** state) |
| `Backport Date` | Timestamp when the backport was committed |
| `Type` | Classification of backport complexity (TYPE-I, TYPE-II, ... TYPE-V) |

## Included Projects (Dataset)

The dataset covers a wide range of Java projects. Note that tooling support may vary (see below).

| Project | Repository | Domain |
|---------|------------|--------|
| **CrateDB** | [crate/crate](https://github.com/crate/crate) | Distributed SQL database |
| **Apache Druid** | [apache/druid](https://github.com/apache/druid) | Real-time analytics database |
| **Elasticsearch** | [elastic/elasticsearch](https://github.com/elastic/elasticsearch) | Search and analytics engine |
| **Apache Hadoop** | [apache/hadoop](https://github.com/apache/hadoop) | Distributed computing framework |
| **Apache Kafka** | [apache/kafka](https://github.com/apache/kafka) | Distributed streaming platform |
| **OpenJDK 8** | [openjdk/jdk8u-dev](https://github.com/openjdk/jdk8u-dev) | Java Development Kit 8 LTS |
| **OpenJDK 11** | [openjdk/jdk11u-dev](https://github.com/openjdk/jdk11u-dev) | Java Development Kit 11 LTS |
| **OpenJDK 17** | [openjdk/jdk17u-dev](https://github.com/openjdk/jdk17u-dev) | Java Development Kit 17 LTS |
| **OpenJDK 21** | [openjdk/jdk21u-dev](https://github.com/openjdk/jdk21u-dev) | Java Development Kit 21 LTS |
| **OpenJDK 25** | [openjdk/jdk25u-dev](https://github.com/openjdk/jdk25u-dev) | Java Development Kit 25 |
| **Graylog** | [Graylog2/graylog2-server](https://github.com/Graylog2/graylog2-server) | Log management |
| **Hibernate ORM** | [hibernate/hibernate-orm](https://github.com/hibernate/hibernate-orm) | JPA implementation |
| **Spring Framework** | [spring-projects/spring-framework](https://github.com/spring-projects/spring-framework) | Java application framework |
| **Logstash** | [elastic/logstash](https://github.com/elastic/logstash) | Data processing pipeline |

-----

# Build & Test Tool

This repository also includes a comprehensive build and test orchestration tool (`reproduce_results.py`). It enables researchers to replicate builds and run regression tests for commits in the dataset using containerized environments.

## Table of Contents

  - [Prerequisites](#prerequisites)
  - [Setup](#setup)
  - [Usage](#usage)
  - [Supported Projects](#supported-projects-tooling)

## Prerequisites

Before using the build tool, ensure you have the following installed:

> **Recommended OS**: Ubuntu/Debian-based Linux (Windows and macOS may require additional configuration)

### Required Software

| Tool | Version | Purpose |
|------|---------|---------|
| **Git** | Latest | Source code management |
| **Python** | 3.8+ | Running build scripts |
| **pip** | Latest | Installing Python dependencies |
| **Docker** | Latest | Containerized build/test environments |

### Docker Setup (Critical)

**Important**: You must configure Docker to run without `sudo` privileges or ensure your user has appropriate permissions.

## Setup

### Step 1: Install Python Dependencies

```bash
pip3 install pandas
```

### Step 2: Clone This Repository

```bash
git clone https://github.com/your-repo/javabackports.git
cd javabackports
```

### Step 3: Set Up Project Repositories

> **Critical Step**: The build scripts expect project repositories to be located in the **parent directory** of this toolkit.

Clone the project repositories you want to test **adjacent** to this repository:

```bash
# Navigate to parent directory
cd ..

# Clone target projects (examples)
git clone https://github.com/crate/crate.git
git clone https://github.com/apache/hadoop.git
# ... (clone other projects as needed)
```

### Required Directory Structure

Your workspace must follow this structure:

```
📁 workspace/
│
├── 📁 javabackports/              ← This repository
│   ├── 📄 reproduce_results.py    ← Main orchestrator
│   ├── 📄 README.md
│   ├── 📁 dataset/                ← Commit datasets
│   └── 📁 helpers/                ← Build & Test logic (per project)
│
├── 📁 crate/                      ← CrateDB repository
├── 📁 hadoop/                     ← Apache Hadoop repository  
└── ...
```

## Usage

All operations are executed from the `javabackports` directory using the `reproduce_results.py` script.

### Command Line Arguments

| Argument | Description | Default |
|----------|-------------|---------|
| `--project` | **(Required)** Name of the project to build (e.g. `crate`, `druid`) | - |
| `--commit` | **(Required)** Commit hash to verify (the backport/fixed commit) | - |
| `--target` | Which versions to run: `fixed`, `buggy`, or `both` | `both` |
| `--no-test` | Skip testing, only run builds | False |

### Examples

**Verify a Backport (Run both Fixed and Buggy versions):**

This builds the fixed commit, runs tests (smartly filtering for modified tests), then builds the parent (buggy) commit, applies the test changes, and runs the same tests to check for regression/fixes.

```bash
python3 reproduce_results.py --project crate --commit <SHA>
```

**Build Fixed Version Only:**

```bash
python3 reproduce_results.py --project elasticsearch --commit <SHA> --target fixed
```

**Build Only (No Tests):**

Useful for verifying compilation if tests are flaky or not needed.

```bash
python3 reproduce_results.py --project hadoop --commit <SHA> --no-test
```

### Supported Projects (Tooling)

The following projects have full build/test support in `reproduce_results.py`:

*   **CrateDB** (`crate`)
*   **Elasticsearch** (`elasticsearch`)
*   **Hadoop** (`hadoop`)
*   **Druid** (`druid`)
*   **Graylog** (`graylog` / `graylog2-server`)
*   **Hibernate ORM** (`hibernate-orm`)
*   **HBase** (`hbase`)
*   **gRPC Java** (`grpc-java`)
*   **Logstash** (`logstash`)
*   **Spring Framework** (`spring-framework`)
*   **SQL** (`sql`)
*   **JDKs** (`jdk11u-dev`, `jdk17u-dev`, `jdk21u-dev`, `jdk25u-dev`)

*(Note: Apache Kafka is included in the dataset but lacks fully automated reproduction scripts at this moment.)*
