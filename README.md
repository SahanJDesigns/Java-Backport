# Java Backports Tooling

Tools for building, testing, and verifying Java backport commits.

## Overview

This repository contains scripts to help automate the verification of backported commits across various Java projects. It includes:

*   `reproduce_results.py`: The main script to reproduce build and test results for a specific commit.
*   `dataset/`: CSVs containing backport data.
*   `helpers/`: Project-specific helpers (Dockerfiles, build scripts).

## Supported Projects

*   CrateDB (`crate`)
*   Elasticsearch (`elasticsearch`)
*   Hadoop (`hadoop`)
*   Druid (`druid`)
*   Graylog (`graylog2-server`)
*   Hibernate ORM (`hibernate-orm`)
*   gRPC Java (`grpc-java`)
*   HBase (`hbase`)
*   JDKs (`jdk11u-dev`, `jdk17u-dev`, `jdk21u-dev`, `jdk25u-dev`)
*   Logstash (`logstash`)
*   Spring Framework (`spring-framework`)
*   SQL (`sql`)

## Setup

1.  **Prerequisites**:
    *   Python 3.x
    *   Docker (running and accessible)
    *   Git (configured)
    *   Repo clones should be siblings to this directory (parent directory of `javabackports`).

2.  **Installation**:
    No specific installation required. Ensure python dependencies (`pandas`) are installed.

## Usage: Reproduce Results

Use `reproduce_results.py` to verify a single backport commit. This script will:
1.  Build and test the **FIXED** version (the backport commit).
2.  Build and test the **BUGGY** version (the parent of the backport commit).
    *   *Note*: It applies test changes from the fixed version to the buggy version to ensure baseline comparison.
3.  Compare results and report fixes/regressions.

### Basic Command

```bash
python3 reproduce_results.py --project <PROJECT_NAME> --commit <COMMIT_SHA>
```

### Options

*   `--target`: Choose which versions to run.
    *   `fixed`: Run only the fixed version.
    *   `buggy`: Run only the buggy version (parent).
    *   `both`: Run both (default).
    
    Example: Run only fixed version checks:
    ```bash
    python3 reproduce_results.py --project crate --commit <SHA> --target fixed
    ```

*   `--no-test`: Skip testing, only run builds. Useful for checking compilation crashes.
    ```bash
    python3 reproduce_results.py --project elasticsearch --commit <SHA> --no-test
    ```

## Adding New Projects

To add a new project, create a directory in `helpers/<project_name>` with:
*   `Dockerfile`: Build environment.
*   `run_build.sh`: Script to compile the project.
*   `run_tests.sh`: Script to run tests.
*   `get_test_targets.py`: Script to identify relevant tests from changed files.

Ensure the project is correctly mapped in the `PROJECT_CONFIG` dictionary in `reproduce_results.py`.
