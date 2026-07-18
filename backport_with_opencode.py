#!/usr/bin/env python3
"""
backport_with_opencode.py — Drive opencode to perform Java backporting from the dataset.

This script runs the `opencode` CLI directly for each row in a dataset CSV, 
auto-approves permission requests, captures the logs, and logs the outcome to Supabase.

Prerequisites:
  pip install supabase python-dotenv

Usage:
  # Configure .env file with NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_SERVICE_KEY
  python backport_with_opencode.py
"""

from dotenv import load_dotenv
import csv
import json
import os
import sys
import time
import traceback
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

try:
    from supabase import create_client, Client
except ImportError:
    print("ERROR: 'supabase' is not installed. Run:  pip install supabase", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# Project Mappings & Git Cloning
# ---------------------------------------------------------------------------

PROJECT_URLS = {
    "crate": "https://github.com/crate/crate.git",
    "druid": "https://github.com/apache/druid.git",
    "elasticsearch": "https://github.com/elastic/elasticsearch.git",
    "hadoop": "https://github.com/apache/hadoop.git",
    "jdk8u-dev": "https://github.com/openjdk/jdk8u-dev.git",
    "jdk11u-dev": "https://github.com/openjdk/jdk11u-dev.git",
    "jdk17u-dev": "https://github.com/openjdk/jdk17u-dev.git",
    "jdk21u-dev": "https://github.com/openjdk/jdk21u-dev.git",
    "jdk25u-dev": "https://github.com/openjdk/jdk25u-dev.git",
    "graylog2-server": "https://github.com/Graylog2/graylog2-server.git",
    "graylog": "https://github.com/Graylog2/graylog2-server.git",
    "hibernate-orm": "https://github.com/hibernate/hibernate-orm.git",
    "spring-framework": "https://github.com/spring-projects/spring-framework.git",
    "logstash": "https://github.com/elastic/logstash.git",
    "hbase": "https://github.com/apache/hbase.git",
    "grpc-java": "https://github.com/grpc/grpc-java.git",
}

def get_or_clone_repo(workspace: Path, project: str) -> Optional[Path]:
    """Return the path to the project repo, cloning it if necessary."""
    repo_dir = workspace / project
    if repo_dir.is_dir() and (repo_dir / ".git").exists():
        return repo_dir
    
    url = PROJECT_URLS.get(project)
    if not url:
        print(f"  [git] No known URL for project '{project}'", file=sys.stderr)
        return None
        
    print(f"  [git] Cloning {url} into {repo_dir}...")
    try:
        subprocess.run(
            ["git", "clone", url, str(repo_dir)],
            check=True,
            capture_output=True,
            text=True
        )
        return repo_dir
    except subprocess.CalledProcessError as e:
        print(f"  [git] Clone failed: {e.stderr}", file=sys.stderr)
        return None


# ---------------------------------------------------------------------------
# Backport prompt builder
# ---------------------------------------------------------------------------

BACKPORT_PROMPT_TEMPLATE = """\
You are an expert Java backporting engineer.

## Task

Your goal is to **backport** a commit from the `{original_version}` branch of the \
`{project}` project to its `{backport_version}` branch.

### Commit information

| Field            | Value |
|------------------|-------|
| Project          | `{project}` |
| Original branch  | `{original_version}` |
| Original commit  | `{original_commit}` |
| Backport branch  | `{backport_version}` |
| Backport commit  | `{backport_commit}` (ground-truth result — do NOT check it out) |
| Backport type    | `{backport_type}` |

The target ref you must apply the patch **to** is the **parent** of the backport commit:
```
{backport_parent}
```
This represents the state of the `{backport_version}` branch *before* the backport was applied.
The repository has already been **checked out to `{backport_parent}`** for you — do NOT switch branches or check out any other ref.
---

## New-version patch to backport

The following is the **exact unified diff** introduced by the original commit `{original_commit}` \
on the `{original_version}` branch. This is the change you must port to `{backport_version}`:

```diff
{new_version_patch}
```

> **Important:** Do **NOT** look at commits that come *after* `{original_commit}` on the \
`{original_version}` branch to infer what to port. The diff above is your sole source of \
truth for what changed. Use git tools only to understand the *context* of the surrounding \
code on the `{backport_version}` branch at ref `{backport_parent}`.

---

## Workflow

Follow these steps in order. Use the available tools at each step.

### Step 1 — Understand the original change
Study the new-version patch above carefully. Identify every file, hunk, and the intent \
of the change. You may also use `git_show {original_commit}` to view the commit message \
and any metadata.

### Step 2 — For each changed hunk, locate the equivalent code on the backport branch
For every significant hunk in the patch above:
1. Use `viewcode` to look at the corresponding file on the backport branch (you are already \
   checked out to `{backport_parent}`).
2. Use `git_history` (limiting to the `{backport_version}` lineage) and `locate_symbol` to \
   find classes, methods, or fields that may have been renamed or relocated.
3. Do **not** traverse child commits of `{original_commit}` on `{original_version}` to \
   gather more patches — use only the diff provided above.

### Step 3 — Construct the backport patch
Based on your analysis, write a unified diff patch that:
- Applies cleanly against ref `{backport_parent}` (current HEAD)
- Preserves the intent of the original change `{original_commit}`
- Adapts to any API or structural differences in `{backport_version}`
- If a hunk is purely new code with no counterpart, mark it as `need not ported`

The patch must follow standard unified diff format with 3 lines of context:
```diff
--- a/path/to/File.java
+++ b/path/to/File.java
@@ -N,M +N,M @@
 context line
-removed line
+added line
 context line
```

### Step 4 — Validate each hunk
Use the `validate` tool with `mode=hunk` and `ref={backport_parent}` to test that each hunk \
applies cleanly. Fix any context mismatches before proceeding.

### Step 5 — Final validation
Call `validate` with `mode=full` and `ref={backport_parent}` to verify the complete patch compiles and passes tests.

### Step 6 — Apply and commit the patch
Once full validation passes, apply the full patch to the working tree and **commit** the \
result so the orchestrator can extract it with `git diff {backport_parent} HEAD`.

---

## Output format

At the end of your work, output the following YAML block so the orchestrator can parse it:

```yaml
backport_result:
  status: success
  patch: |
    <full unified diff here, or empty if need_not_ported>
  notes: >
    <one-line explanation of what was done or why it failed>
```

Valid status values: `success`, `partial`, `failed`, `need_not_ported`

Begin now.
"""


def get_new_version_patch(repo_dir: str, original_commit: str) -> str:
    """Extract the full unified diff of the original (new-version) commit."""
    try:
        result = subprocess.run(
            ["git", "show", "--format=", original_commit],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            check=True,
        )
        patch = result.stdout.strip()
        return patch if patch else "(empty diff — commit may be a merge or metadata-only change)"
    except subprocess.CalledProcessError as e:
        return f"(could not extract patch: {e.stderr.strip()})"
    except Exception as e:
        return f"(unexpected error extracting patch: {e})"


def build_backport_prompt(row: dict, backport_parent: str, new_version_patch: str) -> str:
    return BACKPORT_PROMPT_TEMPLATE.format(
        project=row.get("project", ""),
        original_version=row.get("original_version", "master"),
        original_commit=row.get("original_commit", ""),
        backport_version=row.get("backport_version", ""),
        backport_commit=row.get("backport_commit", ""),
        backport_type=row.get("type", "UNKNOWN"),
        backport_parent=backport_parent,
        new_version_patch=new_version_patch,
    )


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------

def get_parent_commit(repo_dir: str, commit_sha: str) -> Optional[str]:
    """Return the parent SHA of a commit using git rev-parse."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", f"{commit_sha}^"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"  [git] Could not get parent of {commit_sha}: {e.stderr.strip()}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"  [git] Unexpected error getting parent of {commit_sha}: {e}", file=sys.stderr)
        return None


# ---------------------------------------------------------------------------
# Logging helpers
# ---------------------------------------------------------------------------

def _log(log_path: Path, message: str):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {message}"
    print(line, flush=True)
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Post-run Metrics
# ---------------------------------------------------------------------------

def extract_post_run_metrics(repo_dir: str, backport_commit: str, backport_parent: str) -> dict:
    """Extract both the ground-truth (real) patch and the patch generated by opencode.

    The real patch is the diff of the ground-truth backport commit vs its parent.
    The generated patch is what opencode committed on top of backport_parent (i.e.
    everything between backport_parent and the current HEAD after opencode ran).
    If opencode did not commit anything we fall back to the working-tree diff.
    """
    metrics = {
        "old_version_real_patch": "",
        "old_version_generated_patch": "",
        "is_100_percent_similar": False
    }
    try:
        # --- Real (ground-truth) patch ---
        res = subprocess.run(
            ["git", "show", "--format=", backport_commit],
            cwd=repo_dir, capture_output=True, text=True, check=True
        )
        real_patch = res.stdout.strip()
        metrics["old_version_real_patch"] = real_patch

        # --- Generated patch: commits made by opencode on top of backport_parent ---
        res = subprocess.run(
            ["git", "diff", backport_parent, "HEAD"],
            cwd=repo_dir, capture_output=True, text=True, check=True
        )
        gen_patch = res.stdout.strip()

        # If HEAD == backport_parent (opencode made no commit), fall back to
        # the working-tree diff so we still capture any applied-but-uncommitted changes.
        if not gen_patch:
            res = subprocess.run(
                ["git", "diff", backport_parent],
                cwd=repo_dir, capture_output=True, text=True, check=True
            )
            gen_patch = res.stdout.strip()

        metrics["old_version_generated_patch"] = gen_patch

        def clean_patch(p: str) -> str:
            """Strip volatile 'index' lines before comparing."""
            return "\n".join(line for line in p.splitlines()
                            if not line.startswith("index "))

        metrics["is_100_percent_similar"] = (
            clean_patch(real_patch).strip() == clean_patch(gen_patch).strip()
        )
    except Exception as e:
        print(f"Error extracting metrics: {e}")
    return metrics


# ---------------------------------------------------------------------------
# Row processor
# ---------------------------------------------------------------------------

def process_row(
    job: dict,
    workspace: Path,
    log_dir: Path,
    row_index: int,
) -> dict:
    project = job.get("project", "unknown")
    original_commit = job.get("original_commit", "")
    backport_commit = job.get("backport_commit", "")
    backport_type = job.get("type", "?")

    # Per-row log file
    log_path = log_dir / f"{project}_{original_commit[:7]}_{backport_commit[:7]}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    _log(log_path, f"=== Row {row_index}: {project}  {original_commit[:8]} -> {backport_commit[:8]}  [{backport_type}] ===")

    result = {
        "Row": row_index,
        "Project": project,
        "Original Version": job.get("original_version", ""),
        "Original Commit": original_commit,
        "Backport Version": job.get("backport_version", ""),
        "Backport Commit": backport_commit,
        "Type": backport_type,
        "Status": "error",
        "Duration Seconds": 0,
        "Notes": "",
        "Log File": str(log_path),
        "llm_log": ""
    }

    t_start = time.time()

    # 1. Resolve and clone repo
    repo_path = get_or_clone_repo(workspace, project)
    if not repo_path:
        result["Status"] = "error"
        result["Notes"] = f"Could not resolve repository for project {project}"
        _log(log_path, f"  ERROR: {result['Notes']}")
        result["Duration Seconds"] = round(time.time() - t_start, 1)
        return result
    repo_dir = str(repo_path)

    # 2. Resolve the backport parent commit
    _log(log_path, f"  Resolving parent of backport commit {backport_commit[:8]}...")
    backport_parent = get_parent_commit(repo_dir, backport_commit)
    if not backport_parent:
        result["Status"] = "error"
        result["Notes"] = f"Could not resolve parent of backport commit {backport_commit}"
        _log(log_path, f"  ERROR: {result['Notes']}")
        result["Duration Seconds"] = round(time.time() - t_start, 1)
        return result

    _log(log_path, f"  Backport parent (target ref): {backport_parent}")

    # 3. Extract the new-version (original) patch to embed in the prompt
    _log(log_path, f"  Extracting new-version patch for {original_commit[:8]}...")
    new_version_patch = get_new_version_patch(repo_dir, original_commit)
    _log(log_path, f"  New-version patch size: {len(new_version_patch)} chars")

    # 4. Checkout backport_parent so opencode operates on the correct repo state
    _log(log_path, f"  Checking out backport parent {backport_parent[:8]}...")
    try:
        subprocess.run(
            ["git", "checkout", backport_parent],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        result["Status"] = "error"
        result["Notes"] = f"Could not checkout backport parent {backport_parent}: {e.stderr.strip()}"
        _log(log_path, f"  ERROR: {result['Notes']}")
        result["Duration Seconds"] = round(time.time() - t_start, 1)
        return result

    try:
        # 5. Build the prompt (now includes the new-version patch and commit context)
        prompt = build_backport_prompt(job, backport_parent, new_version_patch)
        _log(log_path, f"  Invoking OpenCode CLI ({len(prompt)} chars)...")

        # 6. Invoke opencode CLI directly
        # shell=True is required on Windows so the .cmd script resolves correctly
        # We use Popen + line-by-line streaming so the user sees live output in the
        # terminal (the "UI") while we also capture it for the Supabase log.
        command = f'opencode run --auto --dir "{repo_dir}"'
        
        _log(log_path, f"  Streaming OpenCode CLI output...")

        # Set up env vars so the validate tool can find Docker helpers
        helpers_dir = Path(__file__).resolve().parent / "helpers"
        child_env = os.environ.copy()
        child_env["BACKPORT_HELPERS_DIR"] = str(helpers_dir)
        child_env["BACKPORT_PROJECT"] = project

        proc = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,   # merge stderr into stdout stream
            text=True,
            shell=True,
            bufsize=1,
            encoding="utf-8",
            errors="replace",
            env=child_env,
        )
        # Send the prompt via stdin
        proc.stdin.write(prompt)
        proc.stdin.close()
        
        # Stream line-by-line: print live AND accumulate for log
        captured_lines = []
        for line in proc.stdout:
            print(line, end="", flush=True)   # visible to user
            captured_lines.append(line)

        proc.wait()
        llm_log = "".join(captured_lines)
        
        # Save to result
        result["llm_log"] = llm_log

        # Log the CLI output locally
        with open(log_path, "a", encoding="utf-8") as f:
            f.write("\n--- CLI OUTPUT ---\n")
            f.write(llm_log)
            f.write("\n--- END CLI OUTPUT ---\n")

        # 5. Parse the structured YAML result block from stdout
        status, notes = _parse_result_from_reply(llm_log, log_path)
        result["Status"] = status
        result["Notes"] = notes

    except Exception as e:
        result["Status"] = "error"
        result["Notes"] = f"Unexpected: {str(e)[:200]}"
        _log(log_path, f"  UNEXPECTED ERROR: {traceback.format_exc(limit=3)}")
    finally:
        result["Duration Seconds"] = round(time.time() - t_start, 1)

    _log(log_path, (
        f"  Done in {result['Duration Seconds']}s | "
        f"status={result['Status']}"
    ))
    
    if result["Status"] not in ["error", "fatal_error"]:
        try:
            metrics = extract_post_run_metrics(repo_dir, backport_commit, backport_parent)
            result.update(metrics)
        except Exception:
            pass

    return result


def _parse_result_from_reply(text: str, log_path: Path):
    """
    Parse the YAML result block from the assistant reply.
    Returns (status, notes) tuple.
    """
    if not text:
        return "no_reply", "No assistant reply received"

    import re

    # Primary: look for ```yaml backport_result block
    yaml_match = re.search(
        r"```ya?ml\s*\n(.*?)\n```",
        text,
        re.DOTALL | re.IGNORECASE,
    )

    if yaml_match:
        yaml_text = yaml_match.group(1)
        try:
            import yaml  # type: ignore
            data = yaml.safe_load(yaml_text)
            if isinstance(data, dict):
                br = data.get("backport_result", data)
                status = str(br.get("status", "unknown")).strip()
                notes = str(br.get("notes", "")).strip()
                return status, notes
        except ImportError:
            _log(log_path, "  [parse] PyYAML not installed; using heuristic parsing")
            # Fallback: naive line-by-line parsing
            for line in yaml_text.splitlines():
                if line.strip().startswith("status:"):
                    status = line.split(":", 1)[1].strip()
                    return status, "(parsed without PyYAML)"
        except Exception as e:
            _log(log_path, f"  [parse] YAML parse error: {e}")

    # Fallback: keyword heuristics
    lower = text.lower()
    if "patch applied successfully" in lower or "compiled successfully" in lower:
        return "success", "Detected success keywords in reply"
    if "need not ported" in lower:
        return "need_not_ported", "Marked as need not ported"
    if "context mismatch" in lower or "does not apply" in lower:
        return "failed", "Context mismatch or apply failure detected"
    if "error" in lower and "success" not in lower:
        return "partial", "Errors mentioned in reply without clear success"

    return "unknown", "Could not parse structured result from reply"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    load_dotenv()

    # Hardcoded Configuration
    WORKSPACE = "."
    LIMIT = None
    LOG_DIR = "backport_logs"

    supabase_url = os.environ.get("NEXT_PUBLIC_SUPABASE_URL", "")
    supabase_key = os.environ.get("NEXT_PUBLIC_SUPABASE_SERVICE_KEY", "")

    if not supabase_url or not supabase_key:
        print("ERROR: Must provide NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_SERVICE_KEY in .env file or environment vars", file=sys.stderr)
        sys.exit(1)

    workspace = Path(WORKSPACE).resolve()
    workspace.mkdir(parents=True, exist_ok=True)

    log_dir = Path(LOG_DIR)
    log_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*64}")
    print(f"  OpenCode Backport Automation (CLI Mode)")
    print(f"  Workspace    : {workspace}")
    print(f"  Log dir      : {log_dir}")
    print(f"{'='*64}\n")

    supabase: Client = create_client(supabase_url, supabase_key)
    
    print(f"\nPolling Supabase for 'ready' jobs...\n")

    processed_count = 0
    while True:
        if LIMIT and processed_count >= LIMIT:
            break
            
        res = supabase.table("backport_jobs").select("*").eq("backport_status", "ready").limit(1).execute()
        jobs = res.data
        if not jobs:
            print("No more 'ready' jobs found in Supabase. Exiting.")
            break
            
        job = jobs[0]
        job_id = job["id"]
        
        # Lock job
        supabase.table("backport_jobs").update({"backport_status": "started"}).eq("id", job_id).execute()
        print(f"\nLocked job ID {job_id} ({job.get('project')}: {job.get('original_commit')[:7]})")
        
        try:
            r = process_row(
                job=job,
                workspace=workspace,
                log_dir=log_dir,
                row_index=processed_count + 1,
            )
            
            # Update Supabase
            status = r.get("Status", "error")
            update_data = {
                "backport_status": status,
                "old_version_generated_patch": r.get("old_version_generated_patch", ""),
                "old_version_real_patch": r.get("old_version_real_patch", ""),
                "is_100_percent_similar": r.get("is_100_percent_similar", False),
                "amount_of_token_usage": r.get("amount_of_token_usage", 0),
                "llm_log": r.get("llm_log", "")
            }
            
            # Attempt to update the row. Note: this will fail if 'llm_log' column doesn't exist
            try:
                supabase.table("backport_jobs").update(update_data).eq("id", job_id).execute()
            except Exception as e:
                # If it's a schema error (PGRST204), the user hasn't added the llm_log column yet
                if "PGRST204" in str(e) or "llm_log" in str(e):
                    print(f"Warning: 'llm_log' column not found in Supabase. Falling back to update without it.")
                    update_data.pop("llm_log", None)
                    supabase.table("backport_jobs").update(update_data).eq("id", job_id).execute()
                else:
                    raise e
            
            print(f"Job {job_id} updated with status: {status}")
            processed_count += 1
            
        except KeyboardInterrupt:
            print("\nInterrupted by user. Releasing lock...")
            supabase.table("backport_jobs").update({"backport_status": "ready"}).eq("id", job_id).execute()
            break
        except Exception as e:
            print(f"\nFATAL ERROR on job {job_id}: {e}")
            import traceback
            traceback.print_exc()
            supabase.table("backport_jobs").update({"backport_status": "error"}).eq("id", job_id).execute()

if __name__ == "__main__":
    main()
