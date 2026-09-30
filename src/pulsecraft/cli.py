"""PulseCraft Studio CLI entrypoint (M2: + render post / templates; M3-M5 extend).

Note: the M2 brief names `src/pulsecraft/cli/main.py`, but the shipped entry point
(`pulsecraft.cli:main`, used by M1 commands + tests) stays at `src/pulsecraft/cli.py`
to avoid breaking imports. A `cli/` package split is deferred to M5 if needed.
"""

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


@main.group(name="render")
def render_group() -> None:
    """Render blueprints to export artifacts."""


@render_group.command(name="post")
@click.option("--blueprint", required=True, help="Path to a static-post blueprint JSON file.")
@click.option("--brand", default="acme", show_default=True)
@click.option(
    "--out", default="out", show_default=True, help="Output directory for PNGs + meta.json."
)
@click.option("--layout", default=None, help="Override the blueprint layout id.")
def render_post(blueprint: str, brand: str, out: str, layout: str | None) -> None:
    """Render a static-post blueprint to 1080x1080 + 1080x1350 PNGs."""
    import json
    from pathlib import Path

    from pulsecraft.render_static.renderer import RenderError, StaticPostRenderer

    data = json.loads(Path(blueprint).read_text(encoding="utf-8"))
    if layout:
        data["layout"] = layout
    try:
        result = StaticPostRenderer().render_post(data, brand=brand, out_dir=out)
    except RenderError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"layer: {result.layer} template: {result.template_id}")
    click.echo(f"square: {result.png_square}")
    click.echo(f"vertical: {result.png_vertical}")
    click.echo(f"meta: {result.meta_path}")
    for warning in result.warnings:
        click.echo(f"warning: {warning}")


@main.group(name="templates")
def templates_group() -> None:
    """Inspect and manage decoupled code templates."""


@templates_group.command(name="list")
@click.option("--kind", default="posts", show_default=True, help="Template kind: posts|reels.")
def templates_list(kind: str) -> None:
    """List available templates."""
    from pulsecraft.templates_mgr.manager import TemplateManager

    for info in TemplateManager().list(kind):
        canvases = info.meta.get("supportedCanvas") or info.meta.get("supported canvases") or ""
        click.echo(f"{info.name}: {info.meta.get('displayName', '')} {canvases}")


@templates_group.command(name="inspect")
@click.argument("name")
@click.option("--kind", default="posts", show_default=True)
@click.option("--out", default=None, help="Write badge-tag preview HTML to this path.")
def templates_inspect(name: str, kind: str, out: str | None) -> None:
    """Preview a template with badge tags + show its placeholder schema."""
    from pulsecraft.templates_mgr.manager import TemplateError, TemplateManager

    try:
        preview = TemplateManager().inspect_template(name, kind=kind)
    except TemplateError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"template: {preview['name']} (canvas: {preview['canvas']})")
    click.echo("required: " + (", ".join(preview["schema"]["required"]) or "none"))
    click.echo("optional: " + (", ".join(preview["schema"]["optional"]) or "none"))
    for warning in preview["warnings"]:
        click.echo(f"warning: {warning}")
    if out:
        from pathlib import Path

        Path(out).write_text(preview["html"], encoding="utf-8")
        click.echo(f"preview: {out}")
    else:
        click.echo(preview["html"][:500])


if __name__ == "__main__":
    main()
