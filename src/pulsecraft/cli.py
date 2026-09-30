"""PulseCraft Studio CLI entrypoint (M1: model registry + status; M2-M5 extend)."""

import click


@click.group()
def main() -> None:
    """PulseCraft Studio — prompt to FB/IG PNG + Reels."""


@main.command(name="check-models")
@click.option("--config", default="config/models.json", show_default=True)
def check_models(config: str) -> None:
    """Probe OpenRouter model connectivity (live check, persists results)."""
    from pulsecraft.llm.registry import ModelRegistry, check_model_status

    registry = ModelRegistry.load(config)
    for model_id in registry.to_dict()["registry"]:
        try:
            state = check_model_status(model_id, config)
        except Exception as exc:
            state = f"Failed ({exc})"
        click.echo(f"{model_id}: {state}")


@main.group(name="models")
def models_group() -> None:
    """Model registry: status tables and task fallback chains."""


@models_group.command(name="status")
@click.option("--config", default="config/models.json", show_default=True)
def models_status(config: str) -> None:
    """Display registered models, connection states, and task fallback chains."""
    from pulsecraft.llm.registry import ModelRegistry

    registry = ModelRegistry.load(config)
    data = registry.to_dict()
    click.echo(f"Model registry: {config} (version={data['version']})")
    click.echo("")
    click.echo("Registered models:")
    for model_id, entry in data["registry"].items():
        state = str(entry["status"]).capitalize()
        marker = "Green" if state == "Connected" else "Red" if state == "Failed" else "Gray"
        checked = entry.get("lastChecked") or "never"
        click.echo(
            f"  [{marker}] {model_id} ({entry.get('label', '')}): {state} (checked: {checked})"
        )
    click.echo("")
    click.echo("Task fallback chains:")
    for task, spec in data["tasks"].items():
        click.echo(f"  {task}:")
        for pos, model_id in enumerate(spec["chain"], start=1):
            state = str(data["registry"].get(model_id, {}).get("status", "?")).capitalize()
            click.echo(f"    {pos}. {model_id} [{state}]")


if __name__ == "__main__":
    main()
