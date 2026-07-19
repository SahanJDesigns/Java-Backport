#!/usr/bin/env python3
"""Minimal Supabase REST (PostgREST) client used by run_opencode_backports.py.

Avoids adding a dependency on the full `supabase` SDK: this project only
needs a row existence check (GET) and an insert-or-update against a single
table, both of which PostgREST exposes directly over HTTP.

The table has no unique constraint on (project, backport_commit) — only an
`id` primary key — so upserts here are done manually: look up an existing
row by (project, backport_commit), then PATCH it by id if found, else POST
a new row.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import requests

TABLE = "backport_java_without_tool"

# backport_status defaults to 'ready' when a row is first created; any other
# value means the runner has already produced a result for that row.
PENDING_STATUSES = {None, "", "ready"}


def load_env_file(path: Path) -> None:
    """Populate os.environ from a simple KEY=value .env file, if present.

    Does not override variables already set in the environment.
    """
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


class SupabaseClient:
    def __init__(self, url: str | None = None, key: str | None = None):
        self.url = (url or os.environ.get("SUPABASE_URL", "")).rstrip("/")
        self.key = key or os.environ.get("SUPABASE_KEY", "")
        if not self.url or not self.key:
            raise RuntimeError(
                "SUPABASE_URL and SUPABASE_KEY must be set (env vars or javabackports/.env)."
            )
        self._headers = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
        }

    def get_existing_row(self, project: str, backport_commit: str) -> dict[str, Any] | None:
        response = requests.get(
            f"{self.url}/rest/v1/{TABLE}",
            headers=self._headers,
            params={
                "project": f"eq.{project}",
                "backport_commit": f"eq.{backport_commit}",
                "select": "id,backport_status,is_100_percent_similar",
            },
            timeout=30,
        )
        response.raise_for_status()
        rows = response.json()
        return rows[0] if rows else None

    def row_completed(self, project: str, backport_commit: str) -> bool:
        existing = self.get_existing_row(project, backport_commit)
        if existing is None:
            return False
        return existing.get("backport_status") not in PENDING_STATUSES

    def upsert_result(self, row: dict[str, Any]) -> None:
        project = row["project"]
        backport_commit = row["backport_commit"]
        existing = self.get_existing_row(project, backport_commit)

        if existing is not None:
            response = requests.patch(
                f"{self.url}/rest/v1/{TABLE}",
                headers={**self._headers, "Prefer": "return=minimal"},
                params={"id": f"eq.{existing['id']}"},
                json=row,
                timeout=60,
            )
        else:
            response = requests.post(
                f"{self.url}/rest/v1/{TABLE}",
                headers={**self._headers, "Prefer": "return=minimal"},
                json=row,
                timeout=60,
            )
        if response.status_code >= 400:
            raise RuntimeError(
                f"Supabase upsert failed ({response.status_code}): {response.text}"
            )

    def get_ready_job(self, project: str | None = None) -> dict[str, Any] | None:
        params = {
            "backport_status": "eq.ready",
            "limit": "1"
        }
        if project:
            params["project"] = f"eq.{project}"
            
        response = requests.get(
            f"{self.url}/rest/v1/{TABLE}",
            headers=self._headers,
            params=params,
            timeout=30,
        )
        response.raise_for_status()
        rows = response.json()
        return rows[0] if rows else None

    def lock_job(self, row_id: Any) -> bool:
        response = requests.patch(
            f"{self.url}/rest/v1/{TABLE}",
            headers={**self._headers, "Prefer": "return=representation"},
            params={"id": f"eq.{row_id}", "backport_status": "eq.ready"},
            json={"backport_status": "started"},
            timeout=60,
        )
        response.raise_for_status()
        updated_rows = response.json()
        return len(updated_rows) > 0
        
    def unlock_job(self, row_id: Any, status: str = "ready") -> None:
        response = requests.patch(
            f"{self.url}/rest/v1/{TABLE}",
            headers={**self._headers, "Prefer": "return=minimal"},
            params={"id": f"eq.{row_id}"},
            json={"backport_status": status},
            timeout=60,
        )
        response.raise_for_status()

