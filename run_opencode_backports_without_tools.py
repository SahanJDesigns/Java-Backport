#!/usr/bin/env python3
"""Run OpenCode backport attempts from a javabackports dataset CSV (e.g. crate.csv).

For each CSV row, this script:
  1. Diffs the row's `Original Commit` against its parent to get the
     upstream (latest-version) change that needs to be backported.
  2. Resolves the parent of `Backport Commit` as the base (pre-backport)
     state of the target branch, and materializes it into a fresh, isolated,
     single-commit checkout (not a `git worktree`, which would share the main
     clone's full object database and expose every other branch/commit —
     including the real backport itself — to anything run inside it).
  3. Starts a fresh non-interactive OpenCode session and gives it only the
     upstream diff plus a backport instruction.
  4. Captures OpenCode's generated git diff.
  5. Diffs the base commit against `Backport Commit` to get the ground-truth
     backport, and compares OpenCode's diff against it by applying both to
     the same base and comparing canonical git diffs.
  6. Upserts the result to the Supabase table `backport_java_without_tool`
     (instead of writing a results CSV).

The main project checkout (e.g. ../crate) is never modified; each row gets
its own throwaway checkout under .opencode-backport-worktrees/, removed after
the row completes.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
import textwrap
import time
from pathlib import Path
from typing import Iterable

from supabase_client import SupabaseClient, load_env_file

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
    "sql": "https://github.com/apache/doris.git"
}

def get_or_clone_repo(workspace: Path, project: str) -> Path | None:
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


def _kill_process_tree(process: subprocess.Popen) -> None:
    if os.name == "nt":
        # process.kill() only signals the direct child; opencode.exe spawns
        # its own child process(es), so a plain kill leaves them running as
        # orphans (observed: still consuming tokens minutes after Ctrl+C).
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(process.pid)],
            capture_output=True,
        )
    else:
        process.kill()


def run(
    args: list[str],
    *,
    cwd: Path | None = None,
    input_text: str | None = None,
    timeout: int | None = None,
    check: bool = False,
) -> subprocess.CompletedProcess[str]:
    process = subprocess.Popen(
        args,
        cwd=str(cwd) if cwd else None,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        stdout, stderr = process.communicate(input=input_text, timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_process_tree(process)
        process.communicate()
        raise
    except KeyboardInterrupt:
        _kill_process_tree(process)
        process.communicate()
        raise
    result = subprocess.CompletedProcess(args, process.returncode, stdout, stderr)
    if check and result.returncode != 0:
        cmd = " ".join(args)
        raise RuntimeError(
            f"command failed ({result.returncode}): {cmd}\n"
            f"stdout:\n{result.stdout}\n\nstderr:\n{result.stderr}"
        )
    return result


def require_command(command: str) -> None:
    if shutil.which(command) is None:
        raise RuntimeError(f"required command not found on PATH: {command}")


def resolve_opencode_bin(command: str) -> str:
    found = shutil.which(command)
    if found:
        return found
    raise RuntimeError(
        f"required command not found on PATH: {command}\n"
        "Install OpenCode, add it to PATH, or pass --opencode-bin with the full "
        "path to the OpenCode executable."
    )


def validate_opencode_cli(opencode_bin: str) -> None:
    result = run([opencode_bin, "run", "--help"])
    help_text = result.stdout + result.stderr
    if result.returncode != 0:
        raise RuntimeError(
            "Could not run OpenCode CLI. "
            f"{(result.stderr or result.stdout).strip()}"
        )
    missing_flags = [
        flag for flag in ["--dir", "--format", "--auto"] if flag not in help_text
    ]
    if missing_flags:
        raise RuntimeError(
            "OpenCode CLI is too old for this script; its `run` command is missing "
            f"{', '.join(missing_flags)}. Upgrade OpenCode and try again."
        )


def commit_exists(repo: Path, commit: str) -> bool:
    result = run(["git", "-C", str(repo), "rev-parse", "--verify", f"{commit}^{{commit}}"])
    return result.returncode == 0


def fetch_commit(repo: Path, commit: str) -> None:
    result = run(["git", "-C", str(repo), "fetch", "--no-tags", "origin", commit])
    if result.returncode != 0:
        raise RuntimeError(
            f"Commit not found locally and fetch failed for {commit}: "
            f"{(result.stderr or result.stdout).strip()}"
        )


def ensure_commit_available(repo: Path, commit: str) -> None:
    if not commit_exists(repo, commit):
        fetch_commit(repo, commit)
    if not commit_exists(repo, commit):
        raise RuntimeError(f"Commit not found: {commit}")


def parent_of(repo: Path, commit: str) -> str:
    ensure_commit_available(repo, commit)
    result = run(["git", "-C", str(repo), "rev-parse", f"{commit}^"], check=True)
    parent = result.stdout.strip()
    ensure_commit_available(repo, parent)
    return parent


def diff_between(repo: Path, base: str, head: str) -> str:
    return run(
        ["git", "-C", str(repo), "diff", "--binary", "--no-ext-diff", base, head],
        check=True,
    ).stdout


def git_clean_reset(worktree: Path) -> None:
    run(["git", "-C", str(worktree), "reset", "--hard"], check=True)
    run(["git", "-C", str(worktree), "clean", "-fdxq"], check=True)


def create_isolated_checkout(repo: Path, base_commit: str, dest: Path) -> None:
    """Materialize base_commit into dest as a brand-new, single-commit repo.

    Deliberately NOT `git worktree add`: a linked worktree shares repo's full
    object database and every ref, so the agent working in it could run e.g.
    `git log --all` / `git branch -a` / `git show <sha>` and read the real
    backport straight out of history (release branches like origin/6.1 point
    past base_commit at a tip that already contains this fix, plus every other
    backport ever merged to that branch). A fresh repo populated by a depth-1
    fetch of only base_commit has no other commit or ref reachable, so that
    exploration path finds nothing.
    """
    if dest.exists():
        remove_directory(dest)
    dest.mkdir(parents=True)
    run(["git", "init", "--quiet", str(dest)], check=True)
    # Maven/Gradle build output under target/ routinely produces nested class
    # file paths past Windows' 260-char MAX_PATH (nested/inner classes with
    # long package names); without this, `git clean`/`git status` later fail
    # with "Filename too long" instead of actually cleaning up.
    run(["git", "-C", str(dest), "config", "core.longPaths", "true"], check=True)
    run(
        ["git", "-C", str(dest), "fetch", "--quiet", "--depth", "1", str(repo), base_commit],
        check=True,
    )
    run(["git", "-C", str(dest), "checkout", "--quiet", "--detach", "FETCH_HEAD"], check=True)


def remove_directory(path: Path) -> None:
    """rmtree with retries, tolerating transient Windows file locks (e.g. an
    antivirus/indexer scanning a just-written file, or a still-exiting child
    process) rather than failing the whole row over a race.

    If this is a git checkout, build output (Maven/Gradle target/ dirs) can
    contain paths past Windows' MAX_PATH; unlike git (with core.longPaths set
    in create_isolated_checkout), shutil.rmtree uses plain Win32 file APIs and
    chokes on those. `git clean -fdx` is long-path-aware, so use it to strip
    the offending untracked files first; whatever's left (the originally
    checked-out tracked tree, which doesn't have this problem) rmtree can
    then delete normally.
    """
    if not path.exists():
        return
    if (path / ".git").exists():
        run(["git", "-C", str(path), "clean", "-fdxq"])
    last_error: str = ""
    for attempt in range(5):
        try:
            shutil.rmtree(path)
            return
        except OSError as exc:
            last_error = str(exc)
            if attempt < 4:
                time.sleep(2)
    raise RuntimeError(f"Could not remove directory {path}: {last_error}")


def add_intent_to_add_for_untracked(worktree: Path) -> None:
    status = run(
        ["git", "-C", str(worktree), "status", "--porcelain", "--untracked-files=all"],
        check=True,
    ).stdout
    untracked = [
        line[3:]
        for line in status.splitlines()
        if line.startswith("?? ") and line[3:].strip()
    ]
    if untracked:
        run(["git", "-C", str(worktree), "add", "-N", "--", *untracked], check=True)


def current_diff(worktree: Path) -> str:
    add_intent_to_add_for_untracked(worktree)
    return run(
        ["git", "-C", str(worktree), "diff", "--binary", "--no-ext-diff", "HEAD"],
        check=True,
    ).stdout


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def read_rows(csv_path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise RuntimeError(f"CSV has no header: {csv_path}")
        return list(reader.fieldnames), list(reader)


def format_token_count(value: int | None) -> str:
    return "" if value is None else str(value)


def format_cost(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value, 6)


def parse_opencode_token_usage(jsonl_text: str) -> dict[str, int]:
    usage = {
        "input_tokens": 0,
        "cached_input_tokens": 0,
        "cache_write_tokens": 0,
        "output_tokens": 0,
        "reasoning_output_tokens": 0,
        "total_tokens": 0,
    }
    found_usage = False
    for line in jsonl_text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue

        if event.get("type") != "step_finish":
            continue
        part = event.get("part")
        tokens = part.get("tokens") if isinstance(part, dict) else None
        if not isinstance(tokens, dict):
            continue

        cache = tokens.get("cache")
        cache = cache if isinstance(cache, dict) else {}
        values = {
            "input_tokens": tokens.get("input"),
            "cached_input_tokens": cache.get("read"),
            "cache_write_tokens": cache.get("write"),
            "output_tokens": tokens.get("output"),
            "reasoning_output_tokens": tokens.get("reasoning"),
        }
        for key, value in values.items():
            if isinstance(value, int):
                usage[key] += value
        found_usage = True

    if not found_usage:
        return {}
    usage["total_tokens"] = sum(
        usage[key]
        for key in [
            "input_tokens",
            "cached_input_tokens",
            "cache_write_tokens",
            "output_tokens",
            "reasoning_output_tokens",
        ]
    )
    return usage


def parse_opencode_cost(jsonl_text: str) -> float | None:
    total_cost = 0.0
    found_cost = False
    for line in jsonl_text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict) or event.get("type") != "step_finish":
            continue
        part = event.get("part")
        cost = part.get("cost") if isinstance(part, dict) else None
        if isinstance(cost, (int, float)):
            total_cost += float(cost)
            found_cost = True

    return total_cost if found_cost else None


def parse_opencode_final_message(jsonl_text: str) -> str:
    messages: list[str] = []
    for line in jsonl_text.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict) or event.get("type") != "text":
            continue
        part = event.get("part")
        text = part.get("text") if isinstance(part, dict) else None
        if isinstance(text, str) and text.strip():
            messages.append(text.strip())
    return "\n\n".join(messages)


def parse_opencode_errors(jsonl_text: str) -> str:
    errors: list[str] = []
    for line in jsonl_text.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict) or event.get("type") != "error":
            continue
        error = event.get("error")
        if isinstance(error, dict):
            data = error.get("data")
            message = data.get("message") if isinstance(data, dict) else None
            message = message or error.get("message")
            errors.append(
                str(message)
                if message
                else json.dumps(error, ensure_ascii=False)
            )
        elif error:
            errors.append(str(error))
    return "\n".join(errors)


def render_opencode_event_log(jsonl_text: str) -> str:
    sections: list[str] = []
    for line in jsonl_text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue

        event_type = event.get("type")
        part = event.get("part")
        if event_type == "text" and isinstance(part, dict):
            text = part.get("text")
            if text:
                sections.append(str(text).rstrip())
        elif event_type == "tool_use" and isinstance(part, dict):
            state = part.get("state")
            state = state if isinstance(state, dict) else {}
            block = [f"tool: {part.get('tool', 'unknown')}"]
            tool_input = state.get("input")
            if tool_input is not None:
                block.append(json.dumps(tool_input, ensure_ascii=False, indent=2))
            output = state.get("output") or state.get("error")
            if output:
                block.append(str(output).rstrip())
            sections.append("\n".join(block))
        elif event_type == "step_finish" and isinstance(part, dict):
            tokens = part.get("tokens")
            if isinstance(tokens, dict):
                cache = tokens.get("cache")
                cache = cache if isinstance(cache, dict) else {}
                sections.append(
                    "tokens used\n"
                    f"input: {format_token_count(tokens.get('input'))}\n"
                    f"cache read: {format_token_count(cache.get('read'))}\n"
                    f"cache write: {format_token_count(cache.get('write'))}\n"
                    f"output: {format_token_count(tokens.get('output'))}\n"
                    f"reasoning output: {format_token_count(tokens.get('reasoning'))}"
                )
        elif event_type == "error":
            error = event.get("error")
            if error:
                sections.append(f"error: {json.dumps(error, ensure_ascii=False)}")
    return "\n\n".join(section for section in sections if section).strip() + ("\n" if sections else "")


def build_prompt(project: str, backport_version: str, latest_change: str) -> str:
    return textwrap.dedent(
        f"""\
        Backport the following code change to this checked-out {project} {backport_version} branch.

        Apply the needed source changes directly in the repository. Do not use or
        ask for the older-version patch. Keep the change as small as possible and
        preserve this version's existing style. Do not commit the changes.

        Do not build the project or run its test suite (e.g. mvnw/gradlew/maven/
        test commands) — correctness here is judged purely on the resulting source
        diff, not on a successful build, and building this project is slow and may
        not even be possible in this environment. Only read/edit source files.

        Latest-version change:

        {latest_change}
        """
    )


def run_opencode(
    *,
    worktree: Path,
    prompt: str,
    model: str | None,
    agent: str,
    variant: str | None,
    timeout: int,
    opencode_bin: str,
    log_dir: Path,
    row_number: int,
) -> tuple[int, str, str, str, dict[str, int], float | None, str]:
    command = [
        opencode_bin,
        "run",
        "--dir",
        str(worktree),
        "--agent",
        agent,
        "--format",
        "json",
        "--auto",
        "--title",
        f"crate-backport-row-{row_number:04d}",
    ]
    if model:
        command.extend(["--model", model])
    if variant:
        command.extend(["--variant", variant])

    print(f"  [opencode] Streaming output:")
    process = subprocess.Popen(
        command,
        cwd=str(worktree),
        text=True,
        encoding="utf-8",
        errors="replace",
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=1,
    )
    process.stdin.write(prompt)
    process.stdin.close()
    
    captured_stdout = []
    
    for line in process.stdout:
        captured_stdout.append(line)
        try:
            event = json.loads(line)
            if event.get("type") == "text":
                part = event.get("part", {})
                text = part.get("text", "")
                if text:
                    print(text, end="", flush=True)
            elif event.get("type") == "error":
                error = event.get("error", {})
                print(f"\n[OpenCode Error] {error}\n", flush=True)
        except json.JSONDecodeError:
            pass
            
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_process_tree(process)
        process.wait()
        raise

    raw_stdout = "".join(captured_stdout)
    returncode = process.returncode

    stdout_path = log_dir / "opencode-stdout.txt"
    stderr_path = log_dir / "opencode-stderr.txt"
    write_text(stdout_path, raw_stdout)
    write_text(log_dir / "opencode-events.jsonl", raw_stdout)
    
    readable_log = render_opencode_event_log(raw_stdout)
    write_text(log_dir / "opencode-readable-log.txt", readable_log)
    write_text(stderr_path, "")
    
    final_message = parse_opencode_final_message(raw_stdout)
    error_output = parse_opencode_errors(raw_stdout)
    
    return (
        returncode,
        raw_stdout,
        error_output,
        final_message,
        parse_opencode_token_usage(raw_stdout),
        parse_opencode_cost(raw_stdout),
        readable_log
    )


def canonical_diff_after_applying(worktree: Path, patch_text: str, patch_path: Path) -> tuple[bool, str, str]:
    git_clean_reset(worktree)
    write_text(patch_path, patch_text)
    apply_result = run(
        ["git", "-C", str(worktree), "apply", "--whitespace=nowarn", str(patch_path)]
    )
    if apply_result.returncode != 0:
        return False, "", apply_result.stderr or apply_result.stdout
    return True, current_diff(worktree), ""


def normalize_diff_text(diff_text: str) -> str:
    normalized_lines: list[str] = []
    for raw_line in diff_text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if raw_line.startswith("index "):
            continue
        if raw_line == r"\ No newline at end of file":
            continue
        normalized_lines.append(raw_line)
    return "\n".join(normalized_lines).strip()


def compare_to_expected(
    *,
    worktree: Path,
    generated_diff: str,
    expected_diff: str,
    log_dir: Path,
) -> tuple[bool, str]:
    if not generated_diff.strip():
        return False, "OpenCode produced no git diff."
    if not expected_diff.strip():
        return False, "Could not compute expected backport diff from git history."

    generated_patch = log_dir / "generated.patch"
    expected_patch = log_dir / "expected.patch"
    write_text(generated_patch, generated_diff)
    write_text(expected_patch, expected_diff)

    expected_ok, expected_canonical, expected_error = canonical_diff_after_applying(
        worktree, expected_diff, expected_patch
    )
    if not expected_ok:
        if normalize_diff_text(generated_diff) == normalize_diff_text(expected_diff):
            return True, ""
        return (
            False,
            "Could not apply expected backport diff, and generated diff does not "
            f"textually match it: {expected_error.strip()}",
        )

    generated_ok, generated_canonical, generated_error = canonical_diff_after_applying(
        worktree, generated_diff, generated_patch
    )
    if not generated_ok:
        return False, f"Could not re-apply OpenCode generated diff: {generated_error.strip()}"

    write_text(log_dir / "expected-canonical.patch", expected_canonical)
    write_text(log_dir / "generated-canonical.patch", generated_canonical)

    if expected_canonical == generated_canonical:
        return True, ""
    return False, "Generated code change differs from the expected backport change."


def selected_indexes(total: int, start: int, limit: int | None) -> range:
    start_index = max(start - 1, 0)
    stop = total if limit is None else min(total, start_index + limit)
    return range(start_index, stop)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run OpenCode backport attempts for jobs in Supabase (CLI Mode)."
    )
    parser.add_argument("--workspace", default=Path("."), type=Path, help="Workspace for repos")
    parser.add_argument("--project", default=None, help="Only process jobs for this project (e.g. 'crate').")
    parser.add_argument(
        "--model",
        default=os.environ.get("OPENCODE_MODEL"),
        help=(
            "OpenCode model in provider/model format. Defaults to OPENCODE_MODEL, "
            "then OpenCode's configured default."
        ),
    )
    parser.add_argument(
        "--agent",
        default=os.environ.get("OPENCODE_AGENT", "build"),
        help="OpenCode primary agent to use (default: build).",
    )
    parser.add_argument(
        "--variant",
        default=os.environ.get("OPENCODE_VARIANT"),
        help="Optional provider-specific model variant/reasoning effort.",
    )
    parser.add_argument(
        "--opencode-bin",
        default=os.environ.get("OPENCODE_BIN", "opencode"),
    )
    parser.add_argument("--work-root", default=Path(".opencode-backport-worktrees"), type=Path)
    parser.add_argument("--log-dir", default=Path("opencode-backport-logs"), type=Path)
    parser.add_argument("--start", type=int, default=1, help="1-based CSV row number to start at.")
    parser.add_argument("--limit", type=int, help="Maximum number of rows to process.")
    parser.add_argument(
        "--timeout",
        type=int,
        default=1800,
        help="Per-row OpenCode timeout in seconds.",
    )
    parser.add_argument(
        "--rerun-completed",
        action="store_true",
        help="Run rows even if a Supabase result row already has a success value.",
    )
    parser.add_argument(
        "--keep-worktrees",
        action="store_true",
        help="Do not remove per-row temporary worktrees after processing.",
    )
    args = parser.parse_args()

    require_command("git")
    opencode_bin = resolve_opencode_bin(args.opencode_bin)
    validate_opencode_cli(opencode_bin)
    if args.model and (
        "/" not in args.model
        or args.model.startswith("/")
        or args.model.endswith("/")
    ):
        parser.error("--model must use OpenCode's provider/model format")

    script_dir = Path(__file__).resolve().parent
    load_env_file(script_dir / ".env")
    supabase = SupabaseClient()

    workspace = args.workspace.resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    work_root = args.work_root.resolve()
    log_dir = args.log_dir.resolve()
    log_dir.mkdir(parents=True, exist_ok=True)
    work_root.mkdir(parents=True, exist_ok=True)

    print(f"\nPolling Supabase for 'ready' jobs...\n")

    processed_count = 0
    while True:
        if args.limit and processed_count >= args.limit:
            break
            
        try:
            job = supabase.get_ready_job(args.project)
        except Exception as e:
            print(f"Error polling Supabase: {e}")
            time.sleep(5)
            continue
            
        if not job:
            if args.project:
                print(f"No more 'ready' jobs found for project '{args.project}'. Exiting.")
            else:
                print("No more 'ready' jobs found in Supabase. Exiting.")
            break
            
        job_id = job["id"]
        
        # Lock job (Atomic operation)
        try:
            locked = supabase.lock_job(job_id)
            if not locked:
                print(f"Job {job_id} was already locked by another process/machine. Skipping.")
                continue
        except Exception as e:
            print(f"Failed to lock job {job_id}: {e}")
            time.sleep(1)
            continue
            
        processed_count += 1
        row_number = processed_count
        project = job.get("project", args.project or "unknown").strip()
        original_commit = job.get("original_commit", "").strip()
        backport_commit = job.get("backport_commit", "").strip()

        print(f"[{row_number}] {project} {original_commit[:12]} -> {backport_commit[:12]}")

        repo_path = get_or_clone_repo(workspace, project)
        if not repo_path:
            result = dict(job)
            result["backport_status"] = "error"
            result["Notes"] = f"Could not resolve repository for project {project}"
            supabase.upsert_result(result)
            continue
        repo = repo_path.resolve()

        result: dict[str, object] = {
            "id": job_id,
            "project": project,
            "original_version": (job.get("original_version") or "").strip(),
            "original_commit": original_commit,
            "backport_version": (job.get("backport_version") or "").strip(),
            "backport_commit": backport_commit,
            "backport_date": (job.get("backport_date") or "") or None,
            "type": (job.get("type") or "") or None,
        }
        worktree: Path | None = None

        try:
            row_log_dir = log_dir / f"row-{row_number:04d}"
            row_log_dir.mkdir(parents=True, exist_ok=True)

            ensure_commit_available(repo, original_commit)
            original_parent = parent_of(repo, original_commit)
            latest_change = diff_between(repo, original_parent, original_commit)

            base_commit = parent_of(repo, backport_commit)
            expected_diff = diff_between(repo, base_commit, backport_commit)
            result["old_version_real_patch"] = expected_diff
            print(f"  base: {base_commit[:12]} (parent of backport {backport_commit[:12]})")

            worktree = repo
            try:
                subprocess.run(["git", "-C", str(worktree), "reset", "--hard"], check=True, capture_output=True)
                subprocess.run(["git", "-C", str(worktree), "clean", "-fdxq"], check=True, capture_output=True)
                subprocess.run(
                    ["git", "-C", str(worktree), "checkout", base_commit],
                    check=True,
                    capture_output=True,
                    text=True
                )
            except subprocess.CalledProcessError as e:
                raise RuntimeError(f"Could not checkout backport parent {base_commit}: {e.stderr}")

            prompt = build_prompt(project, str(result.get("backport_version", "")).strip(), latest_change)
            print(f"  worktree path (id): {worktree}")
            code, _stdout, stderr, final_message, token_usage, cost, readable_log = run_opencode(
                worktree=worktree,
                prompt=prompt,
                model=args.model,
                agent=args.agent,
                variant=args.variant,
                timeout=args.timeout,
                opencode_bin=opencode_bin,
                log_dir=row_log_dir,
                row_number=row_number,
            )
            generated_diff = current_diff(worktree)
            success, error = compare_to_expected(
                worktree=worktree,
                generated_diff=generated_diff,
                expected_diff=expected_diff,
                log_dir=row_log_dir,
            )
            if code != 0:
                success = False
                suffix = stderr.strip() or f"OpenCode exited with status {code}."
                error = f"{error} {suffix}".strip()

            result["backport_status"] = "success"
            result["old_version_generated_patch"] = generated_diff
            result["is_100_percent_similar"] = success
            result["amount_of_token_usage"] = token_usage.get("total_tokens")
            
            base_notes = error or (final_message[:2000] if final_message else "")
            result["Notes"] = f"{base_notes}\n\n--- OpenCode Streaming Log ---\n{readable_log}".strip()
            print(
                f"  result: {success}{f' ({error})' if error else ''}"
                f"; tokens={token_usage.get('total_tokens')} cost=${format_cost(cost)}"
            )
        except subprocess.TimeoutExpired:
            result["backport_status"] = "timeout"
            result["is_100_percent_similar"] = None
            result["Notes"] = f"OpenCode timed out after {args.timeout} seconds."
            print(f"  result: timeout ({result['Notes']})")
        except Exception as exc:
            result["backport_status"] = "error"
            result["is_100_percent_similar"] = None
            result["Notes"] = str(exc)
            print(f"  result: error ({exc})")

        try:
            supabase.upsert_result(result)
        except Exception as exc:
            print(f"  WARNING: failed to upsert result to Supabase: {exc}", file=sys.stderr)
            try:
                supabase.unlock_job(job_id, status=str(result.get("backport_status", "error")))
            except Exception:
                pass

    print("done")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        raise SystemExit(130)
