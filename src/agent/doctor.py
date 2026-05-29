"""Project doctor — check your setup, and fix what it safely can.

Run it any time:

    uv run agent-doctor
    # or
    uv run python -m agent.doctor

It reports your environment, shows which credentials are configured, and pings
the live services to confirm they actually work. If DATABASE_URL is set, it also
enables the pgvector extension (safe to run repeatedly). It never makes a paid
model call.
"""

from __future__ import annotations

import asyncio
import platform
import shutil
import subprocess
from pathlib import Path

import httpx
from rich.console import Console
from rich.table import Table

from agent.config import Settings, get_settings
from agent.services.llm import OPENROUTER_BASE_URL

console = Console()

OK = "[green]✓[/green]"
BAD = "[red]✗[/red]"
NA = "[dim]–[/dim]"


def _section(title: str) -> Table:
    table = Table(
        title=title, title_justify="left", title_style="bold", show_header=False, box=None
    )
    table.add_column(no_wrap=True)
    table.add_column()
    table.add_column(style="dim")
    return table


def check_environment() -> Table:
    table = _section("Environment")
    table.add_row(OK, "OS", f"{platform.system()} {platform.release()} ({platform.machine()})")
    table.add_row(OK, "Python", platform.python_version())
    if shutil.which("uv"):
        version = subprocess.run(["uv", "--version"], capture_output=True, text=True).stdout.strip()
        table.add_row(OK, "uv", version)
    else:
        table.add_row(BAD, "uv", "not found on PATH — see https://docs.astral.sh/uv/")
    return table


def ensure_env_file() -> None:
    """Create .env from .env.example on first run so there's something to fill in."""
    env, example = Path(".env"), Path(".env.example")
    if env.exists():
        return
    if example.exists():
        shutil.copyfile(example, env)
        console.print(
            f"{OK} Created [bold].env[/bold] from .env.example — add your keys, then re-run.\n"
        )
    else:
        console.print(f"{BAD} No .env or .env.example found in this folder.\n")


def check_config(settings: Settings) -> Table:
    table = _section("Configuration")
    table.add_row(
        OK if settings.openrouter_api_key else BAD,
        "OPENROUTER_API_KEY",
        "set" if settings.openrouter_api_key else "MISSING — this one is required",
    )
    table.add_row(
        OK if settings.fal_key else NA,
        "FAL_KEY",
        "set" if settings.fal_key else "not set — media generation disabled",
    )
    r2_ok = bool(
        settings.r2_account_id
        and settings.r2_access_key_id
        and settings.r2_secret_access_key
        and settings.r2_bucket
    )
    table.add_row(
        OK if r2_ok else NA, "R2_* (storage)", "set" if r2_ok else "not set — storage disabled"
    )
    table.add_row(
        OK if settings.database_url else NA,
        "DATABASE_URL",
        "set" if settings.database_url else "not set — database disabled",
    )
    return table


async def _check_openrouter(table: Table, settings: Settings) -> None:
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(
                f"{OPENROUTER_BASE_URL}/key",
                headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
            )
        if response.status_code == 200:
            data = response.json().get("data", {})
            limit = data.get("limit")
            detail = f"key valid — used ${data.get('usage', 0)}"
            detail += f", limit ${limit}" if limit is not None else ", no limit"
            table.add_row(OK, "OpenRouter", detail)
        else:
            table.add_row(BAD, "OpenRouter", f"key rejected (HTTP {response.status_code})")
    except Exception as error:  # noqa: BLE001 — a doctor should report, not crash
        table.add_row(BAD, "OpenRouter", f"error: {error}")


async def _check_storage(table: Table, settings: Settings) -> None:
    if not (
        settings.r2_account_id
        and settings.r2_access_key_id
        and settings.r2_secret_access_key
        and settings.r2_bucket
    ):
        table.add_row(NA, "R2 storage", "not configured")
        return
    from agent.services import storage

    try:
        keys = await storage.list_keys()
        table.add_row(OK, "R2 storage", f"reachable — {len(keys)} object(s) under your prefix")
    except Exception as error:  # noqa: BLE001
        table.add_row(BAD, "R2 storage", f"error: {str(error)[:80]}")


async def _check_database(table: Table, settings: Settings) -> None:
    if not settings.database_url:
        table.add_row(NA, "Neon Postgres", "not configured")
        return
    from agent.services import db

    try:
        await db.execute("CREATE EXTENSION IF NOT EXISTS vector")
        row = await db.fetchrow("SELECT version() AS version")
        version = str(row["version"]).split(",")[0] if row else "connected"
        table.add_row(OK, "Neon Postgres", f"connected; pgvector enabled — {version}")
    except Exception as error:  # noqa: BLE001
        table.add_row(BAD, "Neon Postgres", f"error: {str(error)[:90]}")
    finally:
        await db.close_pool()


async def check_live(settings: Settings) -> Table:
    table = _section("Live checks")
    await _check_openrouter(table, settings)
    table.add_row(NA, "fal.ai", "key set (not pinged)" if settings.fal_key else "not configured")
    await _check_storage(table, settings)
    await _check_database(table, settings)
    return table


def main() -> None:
    console.print("\n[bold]🩺  agent doctor[/bold]\n")
    console.print(check_environment())
    console.print()
    ensure_env_file()
    get_settings.cache_clear()  # pick up a freshly created/edited .env
    try:
        settings = get_settings()
    except Exception as error:  # noqa: BLE001
        console.print(f"{BAD} Could not load settings: {error}")
        return
    console.print(check_config(settings))
    console.print()
    console.print(asyncio.run(check_live(settings)))
    console.print()


if __name__ == "__main__":
    main()
