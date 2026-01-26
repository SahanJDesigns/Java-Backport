#!/usr/bin/env python3
import argparse
import subprocess
import sys
import os
import json

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True, help="Path to the git repository")
    parser.add_argument("--commit", required=True, help="Commit hash to analyze")
    args = parser.parse_args()

    # Get list of changed files with status (A=added, M=modified, D=deleted)
    cmd = ["git", "diff-tree", "--no-commit-id", "--name-status", "-r", args.commit]
    try:
        output = subprocess.check_output(cmd, cwd=args.repo, text=True)
    except subprocess.CalledProcessError:
        print(json.dumps({"modified": [], "added": []}))
        return

    modified_tests = set()
    added_tests = set()

    for line in output.strip().splitlines():
        parts = line.split('\t', 1)
        if len(parts) != 2:
            continue
            
        status = parts[0]
        f = parts[1]

        # Only consider Java files that are likely part of a test source set.
        if not f.endswith(".java"):
            continue

        is_test_name = f.endswith("Tests.java") or f.endswith("IT.java")
        # Elasticsearch uses several test source sets (unit, integration, REST, etc.).
        # Treat anything under these as test-related, even if the class name itself
        # is a helper (Constants, *Actions, etc.).
        is_in_test_source = (
            "/src/test/java/" in f
            or "/src/javaRestTest/java/" in f
            or "/src/yamlRestTest/java/" in f
        )

        if not (is_test_name or is_in_test_source):
            # Likely production or build-tool code; we don't derive a specific test target.
            continue
        
        # Find the Gradle module for this file
        head = f
        module_path = ""
        while head:
            head, tail = os.path.split(head)
            if os.path.exists(os.path.join(args.repo, head, "build.gradle")):
                if head == "":
                    module_path = ""
                else:
                    module_path = ":" + head.replace("/", ":")
                break
        
        # Skip if we couldn't find a module
        if module_path == "" and "build.gradle" not in f:
            continue
        
        # Extract test class name and determine task
        try:
            if "/java/" in f:
                # Split path to separate source set from class package
                parts = f.split("/java/")
                pre_java = parts[0] # e.g. .../src/test or .../src/yamlRestTest
                class_part = parts[1] # e.g. org/elasticsearch/FooTests.java
                
                class_name = class_part.replace("/", ".").replace(".java", "")
                
                # Determine task name from source set folder
                # e.g. src/test -> test
                # e.g. src/yamlRestTest -> yamlRestTest
                if "/src/" in pre_java:
                    task_name = pre_java.split("/src/")[-1]
                else:
                    task_name = "test"
                
                # Special handling for QA modules which might not have a 'test' task
                # QA modules usually run via 'check' or custom tasks.
                # Since 'test' is ambiguous or missing, we fallback to 'check' for the whole module.
                if ":qa:" in module_path:
                    test_target = f"{module_path}:check"
                else:
                    test_target = f"{module_path}:{task_name} --tests \"{class_name}\""
            else:
                # Fallback
                test_target = f"{module_path}:test"
            
            # Categorize by status
            if status == 'M':
                modified_tests.add(test_target)
            elif status == 'A':
                added_tests.add(test_target)
        except:
            continue
    
    # Output as JSON with separate lists
    result = {
        "modified": sorted(list(modified_tests)),
        "added": sorted(list(added_tests))
    }
    print(json.dumps(result))

if __name__ == "__main__":
    main()