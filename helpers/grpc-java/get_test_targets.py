#!/usr/bin/env python3
"""
Extract Gradle test targets for grpc-java.
"""
import sys
import os
import subprocess
import json

def get_modified_test_files(repo_dir, commit_sha):
    try:
        # Get list of modified files
        result = subprocess.run(
            f"git diff-tree --no-commit-id --name-only --diff-filter=M -r {commit_sha}",
            shell=True, cwd=repo_dir, capture_output=True, text=True, check=True
        )
        files = [f.strip() for f in result.stdout.splitlines() if f.strip()]
        # Filter for Java test files
        return [f for f in files if f.endswith(".java") and ("test" in f.lower() or "Test" in os.path.basename(f))]
    except:
        return []

def get_added_test_files(repo_dir, commit_sha):
    try:
        # Get list of added files
        result = subprocess.run(
            f"git diff-tree --no-commit-id --name-only --diff-filter=A -r {commit_sha}",
            shell=True, cwd=repo_dir, capture_output=True, text=True, check=True
        )
        files = [f.strip() for f in result.stdout.splitlines() if f.strip()]
        return [f for f in files if f.endswith(".java") and ("test" in f.lower() or "Test" in os.path.basename(f))]
    except:
        return []

def file_to_gradle_target(file_path):
    # Convert path/to/MyTest.java -> --tests "MyTest" (Simple class name matching)
    # Or fully qualified if possible, but package detection requires reading file.
    # Gradle's --tests matches simple names too, e.g. --tests "MyTest"
    filename = os.path.basename(file_path)
    classname = filename.replace(".java", "")
    return f'--tests "{classname}"'

def main():
    repo_dir = None
    commit_sha = None
    
    # Simple manually parsing to avoid complex argparse deps if minimal env
    for i in range(len(sys.argv)):
        if sys.argv[i] == "--repo":
            repo_dir = sys.argv[i+1]
        elif sys.argv[i] == "--commit":
            commit_sha = sys.argv[i+1]

    if not repo_dir or not commit_sha:
        # Check added/modified from git diff locally if not provided
        # But for safety, return ALL or empty
        print(json.dumps({"modified": [], "added": [], "all_targets": "ALL"}))
        return

    modified_files = get_modified_test_files(repo_dir, commit_sha)
    added_files = get_added_test_files(repo_dir, commit_sha)

    modified_targets = [file_to_gradle_target(f) for f in modified_files]
    added_targets = [file_to_gradle_target(f) for f in added_files]
    
    # Combined string for legacy support
    all_targets_list = modified_targets + added_targets
    all_targets_str = " ".join(all_targets_list) if all_targets_list else "NONE"

    print(json.dumps({
        "modified": modified_targets,
        "added": added_targets,
        "all_targets": all_targets_str
    }))

if __name__ == "__main__":
    main()
