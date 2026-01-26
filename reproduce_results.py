#!/usr/bin/env python3
import os
import sys
import subprocess
import argparse
import pandas as pd
import json
import glob
import xml.etree.ElementTree as ET
import re
import shutil
from datetime import datetime

# --- CONFIGURATION ---
PROJECT_CONFIG = {
    "elasticsearch": {
        "repo_name": "elasticsearch", # Added repo_name for compatibility with logic
        "repo_dir": "elasticsearch",
        "report_pattern": "build/test-results/**/*.xml",
        "builder_tag": "es-builder:latest",
        "build_system": "self-building"
    },

    "hadoop": {
        "repo_name": "hadoop",
        "repo_dir": "hadoop",
        "report_pattern": "**/target/surefire-reports/*.xml",
        "builder_tag": "hadoop-builder:latest",
        "build_system": "self-building"
    },
    "druid": {
        "repo_name": "druid",
        "repo_dir": "druid",
        "report_pattern": "**/target/surefire-reports/*.xml",
        "builder_tag": "druid-builder:latest",
        "build_system": "maven"
    },
    "graylog2-server": {
        "repo_name": "graylog2-server",
        "repo_dir": "graylog2-server",
        "report_pattern": "**/target/surefire-reports/*.xml",
        "builder_tag": "graylog-builder:latest",
        "build_system": "maven"
    },
    "jdk11u-dev": {
        "repo_name": "jdk11u-dev",
        "repo_dir": "jdk11u-dev",
        "report_pattern": "**/JTwork/**/*.xml",
        "builder_tag": "jdk11-builder:latest",
        "build_system": "make",
        "boot_jdk": "/opt/java/openjdk",
        "jtreg_home": "/opt/jtreg"
    },
    "jdk17u-dev": {
        "repo_name": "jdk17u-dev",
        "repo_dir": "jdk17u-dev",
        "report_pattern": "**/JTwork/**/*.xml",
        "builder_tag": "jdk17-builder:latest",
        "build_system": "make",
        "boot_jdk": "/opt/java/openjdk",
        "jtreg_home": "/opt/jtreg"
    },
    "jdk21u-dev": {
        "repo_name": "jdk21u-dev",
        "repo_dir": "jdk21u-dev",
        "report_pattern": "**/JTwork/**/*.xml",
        "builder_tag": "jdk21-builder:latest",
        "build_system": "make",
        "boot_jdk": "/opt/java/openjdk",
        "jtreg_home": "/opt/jtreg"
    },
    "jdk25u-dev": {
        "repo_name": "jdk25u-dev",
        "repo_dir": "jdk25u-dev",
        "report_pattern": "**/JTwork/**/*.xml",
        "builder_tag": "jdk25-builder:latest",
        "build_system": "make",
        "boot_jdk": "/opt/java/jdk-24",
        "jtreg_home": "/opt/jtreg"
    },
    "hibernate-orm": {
        "repo_name": "hibernate-orm",
        "repo_dir": "hibernate-orm",
        "report_pattern": "**/*.xml",
        "builder_tag": "hibernate-builder:latest",
        "build_system": "gradle"
    },
    "sql": {
        "repo_name": "sql",
        "repo_dir": "sql",
        "report_pattern": "**/build/test-results/**/*.xml",
        "builder_tag": "sql-builder:latest",
        "build_system": "self-building"
    },
    "logstash": {
        "repo_name": "logstash",
        "repo_dir": "logstash",
        "report_pattern": "**/build/test-results/**/*.xml",
        "builder_tag": "logstash-builder:latest",
        "build_system": "self-building"
    },
    "spring-framework": {
        "repo_name": "spring-framework",
        "repo_dir": "spring-framework",
        "report_pattern": "**/build/test-results/**/*.xml",
        "builder_tag": "spring-builder:latest",
        "build_system": "self-building"
    },
    "hbase": {
        "repo_name": "hbase",
        "repo_dir": "hbase",
        "report_pattern": "**/target/surefire-reports/*.xml",
        "builder_tag": "hbase-builder:latest",
        "build_system": "maven"
    },
    "crate": {
        "repo_name": "crate",
        "repo_dir": "crate",
        "report_pattern": "**/target/surefire-reports/*.xml",
        "builder_tag": "crate-builder:latest",
        "build_system": "self-building"
    },
    "grpc-java": {
        "repo_name": "grpc-java",
        "repo_dir": "grpc-java",
        "report_pattern": "**/*.xml",
        "builder_tag": "grpc-builder:latest",
        "build_system": "gradle"
    }
}

def run_command(command, env=None, check=True, cwd=None, **kwargs):
    if not kwargs.get("capture_output"):
        print(f"CMD: {command}", flush=True)
    process_env = os.environ.copy()
    if env:
        process_env.update(env)
    return subprocess.run(command, shell=True, check=check, env=process_env, cwd=cwd, **kwargs)

def strip_ansi(text):
    return re.sub(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])', '', text)

def parse_console_output(console_text):
    console_text = strip_ansi(console_text)
    passed = set()
    failed = set()

    for match in re.finditer(r"TEST:\s+(.+\.java)\s*\nTEST RESULT:\s*(Passed|Failed)", console_text):
        test_file, result = match.groups()
        clean_name = test_file.replace("/", ".").replace(".java", "")
        if result == "Passed":
            passed.add(clean_name)
        else:
            failed.add(clean_name)

    for match in re.finditer(r"✅ Target\s+(.+?)\s+PASSED", console_text):
        passed.add(match.group(1).replace("test/", "").replace("/", "."))
    for match in re.finditer(r"❌ Target\s+(.+?)\s+FAILED", console_text):
        failed.add(match.group(1).replace("test/", "").replace("/", "."))

    surefire_results = {}
    for match in re.finditer(r"^\[INFO\] Running ([\w.$-]+)", console_text, re.MULTILINE):
        current_class = match.group(1)
        surefire_results[current_class] = {"run": 0, "fail": 0, "error": 0, "skipped": 0}
    for match in re.finditer(r"^\[INFO\] Tests run: (\d+), Failures: (\d+), Errors: (\d+), Skipped: (\d+)[^\n]*-- in ([\w.$-]+)", console_text, re.MULTILINE):
        run, fail, error, skipped, test_class = match.groups()
        run = int(run)
        fail = int(fail)
        error = int(error)
        skipped = int(skipped)
        fail_count = fail + error
        pass_count = run - fail - error - skipped
        for i in range(pass_count):
            passed.add(f"{test_class}.pass_{i+1}")
        for i in range(fail_count):
            failed.add(f"{test_class}.fail_{i+1}")

    summary_match = re.search(r"Test results:\s+passed:\s+(\d+)(?:;\s+failed:\s+(\d+))?", console_text)
    if summary_match and len(passed) == 0 and len(failed) == 0:
        pass_count = int(summary_match.group(1))
        fail_count = int(summary_match.group(2) or 0)
        for i in range(pass_count):
            passed.add(f"TestGroup.passed_{i+1}")
        for i in range(fail_count):
            failed.add(f"TestGroup.failed_{i+1}")

    for match in re.finditer(r"([a-zA-Z0-9_$.]+)\s+>\s+([a-zA-Z0-9_$]+)\s+(PASSED|FAILED|SKIPPED)", console_text):
        cls, method, status = match.groups()
        full_name = f"{cls}.{method}"
        if status == "PASSED":
            passed.add(full_name)
        elif status == "FAILED":
            failed.add(full_name)

    return passed, failed

def parse_test_results(results_dir):
    passed = set()
    failed = set()
    xml_files = glob.glob(os.path.join(results_dir, "**/*.xml"), recursive=True)
    for xml_file in xml_files:
        try:
            tree = ET.parse(xml_file)
            root = tree.getroot()
            for testcase in root.iter('testcase'):
                classname = testcase.get('classname', 'UnknownClass')
                name = testcase.get('name', 'UnknownTest')
                full_name = f"{classname}.{name}"
                if testcase.find('failure') is not None or testcase.find('error') is not None:
                    failed.add(full_name)
                elif testcase.find('skipped') is None:
                    passed.add(full_name)
        except:
            continue
    return passed, failed

def get_modified_test_files(project_dir, commit_sha):
    try:
        result = subprocess.run(
            f"git diff-tree --no-commit-id --name-only --diff-filter=M -r {commit_sha}",
            shell=True, cwd=project_dir, capture_output=True, text=True, check=True
        )
        all_modified = [f.strip() for f in result.stdout.strip().splitlines() if f.strip()]
        test_files = []
        for f in all_modified:
            if any(indicator in f.lower() for indicator in ['test', 'spec']) and f.endswith('.java'):
                test_files.append(f)
        return test_files
    except:
        return []

def apply_test_changes(project_dir, commit_sha, test_files):
    if not test_files:
        return True, "No test files to apply"
    try:
        for test_file in test_files:
            result = subprocess.run(
                f"git show {commit_sha}:{test_file}",
                shell=True, cwd=project_dir, capture_output=True, text=True
            )
            if result.returncode != 0:
                continue
            file_content = result.stdout
            file_path = os.path.join(project_dir, test_file)
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(file_content)
        return True, f"Applied changes to {len(test_files)} test files"
    except Exception as e:
        return False, f"Error applying test changes: {e}"

def compile_and_check_imports(project_dir, test_files, project_name):
    if not test_files:
        return True, "No files to compile", []
    print(f"--- Checking for import errors in {len(test_files)} test files... ---")
    compile_errors = []
    import_errors = []
    if not shutil.which("javac"):
        print("  ⚠️  javac not found on system path. Skipping import checks.")
        return True, "Skipped (javac not found)", []
    
    for test_file in test_files:
        file_path = os.path.join(project_dir, test_file)
        if not os.path.exists(file_path):
            continue
        try:
            result = subprocess.run(
                f"javac -Xlint:all {file_path}",
                shell=True, cwd=project_dir, capture_output=True, text=True, timeout=30
            )
            error_output = result.stderr + result.stdout
            import_error_patterns = [
                r"package .+ does not exist",
                r"cannot find symbol.*import",
                r"class .+ is not public",
                r"cannot access",
            ]
            for pattern in import_error_patterns:
                if re.search(pattern, error_output, re.IGNORECASE):
                    import_errors.append({"file": test_file, "error": error_output})
                    print(f"  ❌ Import error in {test_file}")
                    break
            else:
                if result.returncode != 0:
                    compile_errors.append({"file": test_file, "error": error_output})
        except subprocess.TimeoutExpired:
            print(f"  ⏱️  Compilation timeout for {test_file}")
            continue
        except Exception as e:
            print(f"  ⚠️  Error checking {test_file}: {e}")
            continue
    if import_errors:
        return False, f"Import errors detected in {len(import_errors)} files", import_errors
    return True, "No import errors detected", compile_errors

def get_smart_test_targets(toolkit_dir, project_dir, commit_sha, project_name):
    resolver_script = os.path.join(toolkit_dir, "helpers", project_name, "get_test_targets.py")
    if not os.path.exists(resolver_script):
        return {"modified": [], "added": [], "all_targets": "ALL"}
    try:
        result = subprocess.run(
            f"python3 {resolver_script} --repo {project_dir} --commit {commit_sha}",
            shell=True, capture_output=True, text=True, check=False
        )
        if result.returncode != 0:
             return {"modified": [], "added": [], "all_targets": "ALL"}
        output = result.stdout.strip()
        if not output:
             return {"modified": [], "added": [], "all_targets": "NONE"}
        try:
            data = json.loads(output)
            modified = data.get("modified", [])
            added = data.get("added", [])
            if not modified and not added:
                all_targets = "NONE"
            else:
                all_targets = " ".join(modified + added)
            return {"modified": modified, "added": added, "all_targets": all_targets}
        except json.JSONDecodeError:
            return {"modified": [], "added": [], "all_targets": output}
    except Exception:
        return {"modified": [], "added": [], "all_targets": "ALL"}

def collect_test_reports(project_name, project_repo_dir, dest_dir):
    print(f"--- Scanning {project_repo_dir} for test reports... ---")
    count = 0
    patterns = []
    if "jdk" in project_name:
        patterns = [os.path.join(project_repo_dir, "**/JTwork/**/*.xml"), os.path.join(project_repo_dir, "**/JTreport/**/*.xml")]
    elif PROJECT_CONFIG[project_name]['build_system'] == 'self-building':
        patterns = [os.path.join(project_repo_dir, "all-test-results", "*.xml")]
    else:
        patterns = [os.path.join(project_repo_dir, PROJECT_CONFIG[project_name]["report_pattern"])]

    for full_pattern in patterns:
        for file in glob.glob(full_pattern, recursive=True):
            if file.endswith(".xml"):
                full_src_path = file
                rel_path = os.path.relpath(full_src_path, project_repo_dir)
                dest_path = os.path.join(dest_dir, rel_path)
                os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                try:
                    shutil.copy2(full_src_path, dest_path)
                    count += 1
                except: continue
    print(f"--- Collected {count} test report files. ---")

def execute_lifecycle(project_name, commit_sha, state, toolkit_dir, project_repo_dir, work_dir, test_targets,
                      apply_test_changes_from=None, modified_test_files=None, build_scope=None):
    print(f"\n>>> Processing {state.upper()} state for {commit_sha}...")
    config = PROJECT_CONFIG[project_name]
    state_dir = os.path.join(work_dir, state)
    build_output_dir = os.path.join(state_dir, "build_out")
    test_output_dir = os.path.join(state_dir, "test_out")
    status_file = os.path.join(state_dir, "build_status.txt")
    console_log_file = os.path.join(state_dir, "console.log")
    os.makedirs(build_output_dir, exist_ok=True)
    os.makedirs(test_output_dir, exist_ok=True)

    if apply_test_changes_from and modified_test_files:
        print(f"--- Applying modified test changes from {apply_test_changes_from[:7]} to buggy state ---")
        success, msg = apply_test_changes(project_repo_dir, apply_test_changes_from, modified_test_files)
        if not success:
            return {"build": "Error", "test": "Skipped", "passed": set(), "failed": set(), "error_type": "test_apply_failed", "error_msg": msg}
        # Check for import errors
        has_no_import_errors, check_msg, errors = compile_and_check_imports(project_repo_dir, modified_test_files, project_name)
        if not has_no_import_errors:
             print(f"--- ❌ IMPORT ERROR DETECTED: {check_msg} ---")
             return {"build": "Skipped", "test": "Skipped", "passed": set(), "failed": set(), "error_type": "import_error", "error_msg": check_msg, "import_errors": errors}

    env = {
        "COMMIT_SHA": commit_sha,
        "PROJECT_DIR": project_repo_dir,
        "TOOLKIT_DIR": os.path.join(toolkit_dir, "helpers", project_name),
        "BUILDER_IMAGE_TAG": config['builder_tag'],
        "BUILD_STATUS_FILE": status_file,
        "BUILD_DIR_NAME": f"build_{commit_sha[:7]}_{state}"
    }

    if project_name == "doris" and build_scope:
        env["DORIS_BUILD_SCOPE"] = build_scope

    if config['build_system'] == 'make':
        env["BOOT_JDK"] = config['boot_jdk']
        env["JTREG_HOME"] = config['jtreg_home']
    elif config['build_system'] == 'self-building':
        env["IMAGE_TAG"] = f"{project_name}-{state}-{commit_sha[:7]}"
        env["BUILD_DIR"] = build_output_dir
    elif config['build_system'] in ['gradle', 'maven']:
         env["IMAGE_TAG_TO_BUILD"] = f"{project_name}-{state}-{commit_sha[:7]}"

    build_script = os.path.join(toolkit_dir, "helpers", project_name, "run_build.sh")
    try:
        run_command(f"bash {build_script}", env=env, check=True)
        with open(status_file, 'r') as f:
            build_status = f.read().strip()
    except:
        build_status = "Fail"

    if build_status != "Success":
        return {"build": "Fail", "test": "Skipped", "passed": set(), "failed": set()}

    if test_targets == "NONE":
         return {"build": "Success", "test": "Skipped (No Targets)", "passed": set(), "failed": set()}

    env["TEST_TARGETS"] = test_targets
    env["TEST_REPORT_DIR"] = test_output_dir
    if config['build_system'] == 'self-building':
        env["BUILD_TYPE"] = state

    test_script = os.path.join(toolkit_dir, "helpers", project_name, "run_tests.sh")
    timeout_minutes = 120 if "jdk" in project_name else 60
    console_output = ""

    try:
        with open(console_log_file, "w") as log_file:
            print(f"--- Running tests... ---")
            proc = subprocess.Popen(
                f"bash {test_script}",
                shell=True,
                env={**os.environ, **env},
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            for line in proc.stdout:
                print(line, end='', flush=True)
                log_file.write(line)
                console_output += line
            proc.wait(timeout=timeout_minutes * 60)
            test_status = "Success" if proc.returncode == 0 else "Fail"
    except subprocess.TimeoutExpired:
        print(f"\n!!! Test execution timed out after {timeout_minutes} minutes !!!")
        proc.kill()
        proc.wait()
        test_status = "Timeout"
    except Exception as e:
        print(f"Error running tests: {e}")
        test_status = "Error"

    source_dir = project_repo_dir
    if config['build_system'] == 'self-building':
        source_dir = build_output_dir
    collect_test_reports(project_name, source_dir, test_output_dir)
    passed, failed = parse_test_results(test_output_dir)

    if len(passed) == 0 and len(failed) == 0:
        log_passed, log_failed = parse_console_output(console_output)
        if len(log_passed) > 0 or len(log_failed) > 0:
            passed, failed = log_passed, log_failed
        elif test_status == "Fail":
             test_status = "Crash/No Report"

    return {"build": build_status, "test": test_status, "passed": passed, "failed": failed}

def main():
    parser = argparse.ArgumentParser(description="Reproduce results for a specific Java backport commit.")
    parser.add_argument("--project", required=True, choices=PROJECT_CONFIG.keys())
    parser.add_argument("--commit", required=True, help="Hash of the backport commit (the 'fixed' state).")
    parser.add_argument("--target", choices=['fixed', 'buggy', 'both'], default='both', help="Which versions to run.")
    parser.add_argument("--no-test", action="store_true", help="Skip running tests (build only).")
    
    args = parser.parse_args()

    project_name = args.project
    commit_sha = args.commit
    toolkit_dir = os.getcwd()
    config = PROJECT_CONFIG[project_name]
    repo_dir = config["repo_dir"]
    project_repo_dir = os.path.abspath(os.path.join(toolkit_dir, "..", repo_dir))
    
    if not os.path.exists(project_repo_dir):
        print(f"Error: Repository directory {project_repo_dir} not found.")
        sys.exit(1)

    print(f"=== Reproducing Results for {project_name} @ {commit_sha} ===")
    
    # Identify parent commit
    try:
        res = subprocess.run(f"git rev-parse {commit_sha}^", shell=True, cwd=project_repo_dir, capture_output=True, text=True, check=True)
        parent_sha = res.stdout.strip()
        print(f"Parent Commit (Buggy): {parent_sha}")
    except:
        print("Error: Could not determine parent commit. Ensure {commit_sha} exists in {project_repo_dir}")
        sys.exit(1)

    work_dir = os.path.join(toolkit_dir, "reproduce_work", f"{project_name}_{commit_sha[:7]}")
    if os.path.exists(work_dir):
        shutil.rmtree(work_dir)
    os.makedirs(work_dir)

    # Build builder image if needed
    if config['build_system'] != 'self-building':
        dockerfile = os.path.join(toolkit_dir, "helpers", project_name, "Dockerfile")
        print(f"--- Building Builder Image ---")
        subprocess.run(f"docker build -t {config['builder_tag']} -f {dockerfile} {os.path.dirname(dockerfile)}", shell=True, check=True)

    # Get test targets
    print(f"--- Calculating Test Targets ---")
    targets_data = get_smart_test_targets(toolkit_dir, project_repo_dir, commit_sha, project_name)
    modified_tests = targets_data["modified"]
    added_tests = targets_data["added"]
    all_targets = targets_data["all_targets"]
    print(f"Test Targets: {all_targets}")
    
    modified_test_files = get_modified_test_files(project_repo_dir, commit_sha)
    
    doris_build_scope = None
    if project_name == "doris":
        # Simplified scope logic
        doris_build_scope = "FE_ONLY" # Default to FE for speed unless we want full
        print(f"--- Doris Build Scope: {doris_build_scope} ---")

    # Run Fixed
    after_res = {"build": "Skipped", "test": "Skipped", "passed": set(), "failed": set()}
    if args.target in ['fixed', 'both']:
        # Ensure clean state
        subprocess.run(f"git clean -fd && git checkout -f {commit_sha}", shell=True, cwd=project_repo_dir, check=True)
        
        test_cmd = "NONE" if args.no_test else all_targets
        after_res = execute_lifecycle(project_name, commit_sha, "fixed", toolkit_dir, project_repo_dir, work_dir, test_cmd, build_scope=doris_build_scope)

    # Run Buggy
    before_res = {"build": "Skipped", "test": "Skipped", "passed": set(), "failed": set()}
    if args.target in ['buggy', 'both']:
        # Ensure clean state and checkout parent
        subprocess.run(f"git clean -fd && git checkout -f {parent_sha}", shell=True, cwd=project_repo_dir, check=True)
        
        test_cmd = "NONE" if args.no_test else all_targets
        apply_from = None
        mod_files = None
        
        # Apply test changes logic
        if not args.no_test and modified_test_files:
             apply_from = commit_sha
             mod_files = modified_test_files
             test_cmd = " ".join(modified_tests + added_tests) if modified_tests else all_targets # If we have modified tests, run specific. 

        before_res = execute_lifecycle(project_name, parent_sha, "buggy", toolkit_dir, project_repo_dir, work_dir, test_cmd,
                                       apply_test_changes_from=apply_from, modified_test_files=mod_files, build_scope=doris_build_scope)

    # Compare
    print("\n" + "="*60)
    print(f"SUMMARY REPORT: {project_name} {commit_sha}")
    print("="*60)
    
    print(f"FIXED VERSION ({commit_sha[:7]}):")
    print(f"  Build: {after_res['build']}")
    print(f"  Test:  {after_res['test']}")
    print(f"  Passed: {len(after_res['passed'])}, Failed: {len(after_res['failed'])}")
    
    print(f"BUGGY VERSION ({parent_sha[:7]}):")
    print(f"  Build: {before_res['build']}")
    print(f"  Test:  {before_res['test']}")
    print(f"  Passed: {len(before_res['passed'])}, Failed: {len(before_res['failed'])}")
    
    if args.target == 'both' and after_res['test'] == 'Success' and (before_res['test'] == 'Success' or before_res['test'] == 'Fail'):
        fixes = list(before_res["failed"].intersection(after_res["passed"]))
        regressions = list(before_res["passed"].intersection(after_res["failed"]))
        new_passes = list(after_res["passed"].difference(before_res["passed"].union(before_res["failed"])))
        
        print("-" * 60)
        print(f"Regressions: {len(regressions)}")
        for t in regressions: print(f"  - {t}")
        print(f"Fixes: {len(fixes)}")
        for t in fixes: print(f"  - {t}")
        print(f"New Passes: {len(new_passes)}")
    
    print("="*60)
    print(f"Artifacts preserved in: {work_dir}")

if __name__ == "__main__":
    main()
