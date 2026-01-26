#!/usr/bin/env python3
import argparse
import subprocess
import sys
import os
import json

# Modules known to be broken/require complex envs that we want to skip
BLACKLIST_MODULES = [
    "hadoop-yarn-project/hadoop-yarn/hadoop-yarn-applications/hadoop-yarn-applications-catalog/hadoop-yarn-applications-catalog-webapp",
    "hadoop-yarn-project/hadoop-yarn/hadoop-yarn-applications/hadoop-yarn-applications-catalog/hadoop-yarn-applications-catalog-docker",
]

def is_blacklisted(module_path):
    for bad in BLACKLIST_MODULES:
        if module_path == bad or module_path.startswith(bad + "/"):
            return True
    return False

def find_module_for_file(repo, filepath):
    """Find the Maven module (directory with pom.xml) for a given file."""
    current_dir = os.path.dirname(filepath) if filepath else ""
    
    while current_dir:
        pom_path = os.path.join(repo, current_dir, "pom.xml")
        if os.path.exists(pom_path):
            if not is_blacklisted(current_dir):
                return current_dir
            else:
                return None  # Blacklisted module
        parent = os.path.dirname(current_dir)
        if parent == current_dir:
            break
        current_dir = parent
    
    return None

def extract_test_class(filepath):
    """Extract the fully qualified test class name from a test file path."""
    if "/src/test/java/" not in filepath:
        return None
    
    try:
        class_part = filepath.split("/src/test/java/")[1]
        class_name = class_part.replace("/", ".").replace(".java", "")
        return class_name
    except:
        return None

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True, help="Path to the git repository")
    parser.add_argument("--commit", required=True, help="Commit hash to analyze")
    args = parser.parse_args()

    # 1. Get list of changed files with status
    cmd = ["git", "diff-tree", "--no-commit-id", "--name-status", "-r", args.commit]
    try:
        output = subprocess.check_output(cmd, cwd=args.repo, text=True)
    except subprocess.CalledProcessError:
        print(json.dumps({"modified": [], "added": []}))
        return

    modified_tests = set()
    added_tests = set()

    lines = output.strip().splitlines()
    
    # Process ALL files, but only extract test files
    for line in lines:
        parts = line.split('\t')
        if not parts:
            continue
            
        status = parts[0]
        
        # Handle Renames (R) and Copies (C) which have 3 parts: status, old_path, new_path
        if status.startswith('R') or status.startswith('C'):
            if len(parts) >= 3:
                filepath = parts[2]
            else:
                continue
        else:
            if len(parts) >= 2:
                filepath = parts[1]
            else:
                continue
        
        filename = os.path.basename(filepath)
        
        # Only process test files
        # Fixed logic to include files starting with 'Test'
        is_test_file = (
            "/src/test/java/" in filepath and 
            filepath.endswith(".java") and
            (filename.startswith("Test") or filename.endswith("Test.java") or filename.endswith("Tests.java") or filename.endswith("IT.java"))
        )
        
        if not is_test_file:
            continue
            
        # Find module for this test file
        module = find_module_for_file(args.repo, filepath)
        if not module:
            continue
        
        # Extract test class name
        test_class = extract_test_class(filepath)
        if not test_class:
            continue
        
        # Create target in format: module:fully.qualified.TestClass
        target = f"{module}:{test_class}"
        
        if status == 'A':
            added_tests.add(target)
        else:
            modified_tests.add(target)
    
    # Return only the test files that were modified or added
    result = {
        "modified": sorted(list(modified_tests)),
        "added": sorted(list(added_tests))
    }
    
    print(json.dumps(result))

if __name__ == "__main__":
    main()