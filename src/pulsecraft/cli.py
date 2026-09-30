"""PulseCraft Studio CLI entrypoint (M0 scaffold; full commands land in M1-M5)."""

import click


@click.group()
def main() -> None:
    """PulseCraft Studio — prompt to FB/IG PNG + Reels."""


@main.command(name="check-models")
@click.option("--config", default="config/models.json", show_default=True)
def check_models(config: str) -> None:
    """Probe OpenRouter model connectivity (M1 implements; M0 stub)."""
    from pulsecraft.llm.registry import load_model_registry

    registry = load_model_registry(config)
    click.echo(f"Loaded registry version={registry.get('version')} config={config}")


if __name__ == "__main__":
    main()
