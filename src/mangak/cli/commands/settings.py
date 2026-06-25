"""mangak settings — Show or modify application settings."""

from __future__ import annotations

from typing import Optional

import typer
from rich.console import Console

from mangak.core import ConfigError, Settings
from mangak.cli.display import build_settings_table


def settings_cmd(set_key: Optional[str] = None) -> None:
    """Display or modify application settings.

    Use --set "key=value" to change a setting.
    """
    settings = Settings()
    console = Console()

    if set_key:
        _set_setting(settings, set_key)
        return

    # Display current settings
    all_settings = settings.all()
    table = build_settings_table(all_settings)
    console.print(table)
    console.print()
    console.print("[dim]Use --set \"key=value\" to modify a setting.[/dim]")


def _set_setting(settings: Settings, key_value: str) -> None:
    """Parse and apply a 'key=value' setting."""
    console = Console()

    if "=" not in key_value:
        console.print(
            f"[red]❌ Invalid format. Use --set \"key=value\"[/red]"
        )
        raise typer.Exit(code=1)

    key, _, raw_val = key_value.partition("=")
    key = key.strip()
    raw_val = raw_val.strip()

    if not key or raw_val is None:
        console.print(
            f"[red]❌ Invalid format. Use --set \"key=value\"[/red]"
        )
        raise typer.Exit(code=1)

    # Type coercion based on current value
    current = settings.get(key)
    if current is None:
        # Unknown key — check defaults
        default_settings = Settings().all()
        current = default_settings.get(key)

    if current is None:
        console.print(f"[yellow]⚠️  Unknown setting: '{key}'[/yellow]")
        console.print("[dim]Run 'mangak settings' to see all available settings.[/dim]")
        raise typer.Exit(code=1)

    try:
        if isinstance(current, bool):
            val = raw_val.lower() in ("true", "1", "yes", "on")
        elif isinstance(current, int):
            val = int(raw_val)
        elif isinstance(current, float):
            val = float(raw_val)
        else:
            val = raw_val
    except (ValueError, TypeError):
        console.print(
            f"[red]❌ Invalid value '{raw_val}' for '{key}' "
            f"(expected {type(current).__name__})[/red]"
        )
        raise typer.Exit(code=1)

    try:
        settings.set(key, val)
    except ConfigError as exc:
        console.print(f"[red]❌ {exc}[/red]")
        raise typer.Exit(code=1)

    console.print(f"[green]✅ Set '{key}' to '{str(val)}'[/green]")
    console.print("[dim]Run 'mangak settings' to verify.[/dim]")
