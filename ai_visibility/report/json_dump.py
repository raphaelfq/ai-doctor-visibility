"""JSON reporter — dumps the complete Report as report.json."""

from pathlib import Path

from ai_visibility.models import Report


def dump_json(report: Report, output_dir: Path) -> Path:
    path = output_dir / "report.json"
    path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    return path
