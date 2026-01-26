#!/usr/bin/env python3
import argparse
import subprocess
import sys
import os
import json

def find_gradle_module(repo, filepath):
    """
    Finds the Gradle module path (e.g. :spring-web or :spring-context) for a given file.
    For Spring Framework and similar projects, extracts module from path structure.
    """
    # filepath is relative to repo root, e.g. "spring-web/src/test/java/..."
    
    # Spring Framework pattern: module-name/src/test/...
    # Extract the first directory component before /src/
    if "/src/" in filepath or "\\src\\" in filepath:
        normalized_path = filepath.replace("\\", "/")
        parts = normalized_path.split("/src/")
        if len(parts) >= 2:
            # The module is the directory before /src/
            module_dir = parts[0]
            if module_dir and "/" not in module_dir:
                # Single-level module like "spring-web"
                return ":" + module_dir
            elif module_dir and "/" in module_dir:
                # Multi-level module like "integration-tests/spring-web"
                return ":" + module_dir.replace("/", ":")
    
    # Fallback: walk up directory tree looking for build.gradle
    current_dir = os.path.dirname(filepath)
    
    while current_dir:
        build_gradle_path = os.path.join(repo, current_dir, "build.gradle")
        build_gradle_kts_path = os.path.join(repo, current_dir, "build.gradle.kts")
        
        if os.path.exists(build_gradle_path) or os.path.exists(build_gradle_kts_path):
            normalized_dir = current_dir.replace("\\", "/")
            return ":" + normalized_dir.replace("/", ":")
            
        parent = os.path.dirname(current_dir)
        if parent == current_dir:
            break
        current_dir = parent
        
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
    
    for line in lines:
        parts = line.split('\t')
        if not parts:
            continue
            
        status = parts[0]
        
        # Handle Renames (R) and Copies (C)
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
        
        # Only process test files
        filename = os.path.basename(filepath)
        is_test_file = (
            "/src/test/" in filepath and 
            (filepath.endswith(".java") or filepath.endswith(".kotlin") or filepath.endswith(".scala") or filepath.endswith(".groovy")) and
            (filename.startswith("Test") or filename.endswith("Test.java") or 
             filename.endswith("Tests.java") or filename.endswith("TestCase.java") or
             filename.endswith("IT.java") or filename.endswith("IntegrationTest.java"))
        )
        
        if not is_test_file:
            continue
            
        # Find the Gradle module
        module_path = find_gradle_module(args.repo, filepath)
        if not module_path:
            print(f"DEBUG: Could not determine module for: {filepath}", file=sys.stderr)
            continue
        
        test_target = ""
        
        try:
            # Extract class name. 
            # Path: spring-core/src/test/java/org/springframework/util/MyTest.java
            # Want: org.springframework.util.MyTest
            
            rel_path = ""
            if "/src/test/java/" in filepath:
                rel_path = filepath.split("/src/test/java/")[1]
            elif "/src/test/kotlin/" in filepath:
                rel_path = filepath.split("/src/test/kotlin/")[1]
            elif "/src/test/groovy/" in filepath:
                rel_path = filepath.split("/src/test/groovy/")[1]
            
            if rel_path:
                class_name = rel_path.replace("/", ".").replace("\\", ".").rsplit(".", 1)[0]
                # Gradle syntax for single test
                test_target = f"{module_path}:test --tests \"{class_name}\""
            else:
                # Fallback to module test if we can't parse the class path
                test_target = f"{module_path}:test"
                
        except IndexError:
            # Fallback
            test_target = f"{module_path}:test"

        if test_target:
            if status == 'A':
                added_tests.add(test_target)
            else:
                modified_tests.add(test_target)

    # Output as JSON
    result = {
        "modified": sorted(list(modified_tests)),
        "added": sorted(list(added_tests))
    }
    print(json.dumps(result))

if __name__ == "__main__":
    main()
