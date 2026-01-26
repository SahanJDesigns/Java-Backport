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
        filepath = parts[1].replace("\\", "/")
        
        # Check if it's a test file (contains "test/" in path and ends with .java)
        if "test/" in filepath and filepath.endswith(".java"):
            if status == 'M':
                modified_tests.add(filepath)
            elif status == 'A':
                added_tests.add(filepath)
    
    # Output as JSON with separate lists
    result = {
        "modified": sorted(list(modified_tests)),
        "added": sorted(list(added_tests))
    }
    print(json.dumps(result))

if __name__ == "__main__":
    main()
