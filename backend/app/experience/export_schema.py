"""Export the experience JSON Schema to `extraction/schema.json`.

Usage:
    uv run workstory-export-schema
"""

import json
from pathlib import Path

from app.experience.models import ExperienceFile

SCHEMA_PATH = Path(__file__).resolve().parents[3] / "extraction" / "schema.json"


def render_schema() -> str:
    return json.dumps(ExperienceFile.model_json_schema(), indent=2) + "\n"


def main() -> None:
    SCHEMA_PATH.write_text(render_schema(), encoding="utf-8")
    print(f"Wrote {SCHEMA_PATH}")


if __name__ == "__main__":
    main()
