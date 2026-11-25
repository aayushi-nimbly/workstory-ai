import json

import pytest

from app.experience.export_schema import SCHEMA_PATH, render_schema
from app.experience.validate import main, validate_data, validate_file


def error_messages(data: dict) -> list[str]:
    return [f"{i.path}: {i.message}" for i in validate_data(data).errors]


def warning_messages(data: dict) -> list[str]:
    return [f"{i.path}: {i.message}" for i in validate_data(data).warnings]


def assert_error(data: dict, fragment: str) -> None:
    messages = error_messages(data)
    assert any(fragment in m for m in messages), f"'{fragment}' not in {messages}"


# ---------- Valid file ----------


def test_valid_file_passes(valid_data):
    result = validate_data(valid_data)
    assert result.is_valid
    assert result.issues == []


# ---------- Field-level rules ----------


def test_unknown_field_rejected(valid_data):
    valid_data["projects"][0]["descripton"] = "typo"
    assert_error(valid_data, "projects[0].descripton: Extra inputs are not permitted")


def test_blank_required_text_rejected(valid_data):
    valid_data["projects"][0]["name"] = "   "
    assert_error(valid_data, "projects[0].name")


def test_bad_id_format_rejected(valid_data):
    valid_data["projects"][0]["id"] = "Proj Cache"
    assert_error(valid_data, "projects[0].id")


def test_invalid_enum_rejected(valid_data):
    valid_data["projects"][0]["skills"][0]["involvement"] = "expert"
    assert_error(valid_data, "projects[0].skills[0].involvement")


def test_unsupported_schema_version_rejected(valid_data):
    valid_data["metadata"]["schema_version"] = "2.0"
    assert_error(valid_data, "metadata.schema_version")


def test_project_needs_contributions(valid_data):
    valid_data["projects"][0]["my_contributions"] = []
    assert_error(valid_data, "projects[0].my_contributions")


def test_merged_pr_needs_merge_date(valid_data):
    valid_data["pull_requests"][0]["merged_at"] = None
    assert_error(valid_data, "'merged_at' is required when status is 'merged'")


def test_open_pr_cannot_have_merge_date(valid_data):
    valid_data["pull_requests"][0]["status"] = "open"
    assert_error(valid_data, "'merged_at' must be empty unless status is 'merged'")


def test_merge_before_creation_rejected(valid_data):
    valid_data["pull_requests"][0]["merged_at"] = "2025-12-01"
    assert_error(valid_data, "cannot be earlier than 'created_at'")


def test_metric_needs_evidence(valid_data):
    del valid_data["projects"][0]["metrics"][0]["evidence"]
    assert_error(valid_data, "projects[0].metrics[0].evidence")


def test_metric_values_need_unit(valid_data):
    valid_data["projects"][0]["metrics"][0]["unit"] = None
    assert_error(valid_data, "'unit' is required")


# ---------- Cross-record rules ----------


def test_duplicate_project_id(valid_data):
    valid_data["projects"].append(dict(valid_data["projects"][0]))
    assert_error(valid_data, "duplicate project id 'proj-cache'")


def test_duplicate_skill_name_case_insensitive(valid_data):
    valid_data["skills"].append({"name": "redis", "category": "Databases"})
    assert_error(valid_data, "duplicate skill name 'redis'")


def test_alias_clashing_with_skill_name(valid_data):
    valid_data["skills"].append({"name": "Python", "category": "Languages", "aliases": ["Redis"]})
    assert_error(valid_data, "alias 'Redis' is also a skill name")


def test_unknown_category(valid_data):
    valid_data["projects"][0]["categories"] = ["Backend"]
    assert_error(valid_data, "unknown category 'Backend'")


def test_category_case_hint(valid_data):
    valid_data["projects"][0]["categories"] = ["performance optimisation"]
    assert_error(valid_data, "did you mean 'Performance Optimisation'?")


def test_unknown_skill(valid_data):
    valid_data["projects"][0]["skills"][0]["name"] = "Kafka"
    assert_error(valid_data, "unknown skill 'Kafka'")


def test_alias_used_instead_of_canonical_skill(valid_data):
    valid_data["projects"][0]["skills"][0]["name"] = "redis-py"
    assert_error(valid_data, "use the canonical skill name 'Redis'")


def test_duplicate_skill_in_project(valid_data):
    skills = valid_data["projects"][0]["skills"]
    skills.append(dict(skills[0]))
    assert_error(valid_data, "skill 'Redis' is listed more than once")


def test_project_references_unknown_pr(valid_data):
    valid_data["projects"][0]["pr_ids"].append("pr-99")
    assert_error(valid_data, "unknown pull request 'pr-99'")


def test_pr_references_unknown_project(valid_data):
    valid_data["pull_requests"][0]["project_id"] = "proj-missing"
    assert_error(valid_data, "unknown project 'proj-missing'")


def test_pr_not_listed_by_its_project(valid_data):
    valid_data["projects"][0]["pr_ids"] = ["pr-1"]
    assert_error(valid_data, "does not list this PR")


def test_project_lists_pr_owned_by_other_project(valid_data):
    valid_data["pull_requests"][1]["project_id"] = None
    assert_error(valid_data, "'pr-2' is listed here but its project_id is 'None'")


def test_decision_cites_pr_outside_project(valid_data):
    valid_data["pull_requests"].append(
        {
            "id": "pr-3",
            "title": "Unrelated",
            "summary": "Unrelated change.",
            "contribution": "Small fix.",
            "created_at": "2026-02-01",
            "status": "open",
            "confidence": "low",
        }
    )
    valid_data["projects"][0]["decisions"][0]["pr_ids"] = ["pr-3"]
    assert_error(valid_data, "'pr-3' is not one of this project's PRs")


def test_standalone_pr_without_project_is_allowed(valid_data):
    valid_data["pull_requests"].append(
        {
            "id": "pr-3",
            "title": "Chore",
            "summary": "Dependency bump.",
            "contribution": "Bumped versions.",
            "created_at": "2026-02-01",
            "status": "open",
            "confidence": "high",
        }
    )
    assert validate_data(valid_data).is_valid


# ---------- Warnings (file still valid) ----------


def test_unused_skill_and_category_warn(valid_data):
    valid_data["skills"].append({"name": "Go", "category": "Languages"})
    valid_data["categories"].append({"name": "Security"})
    result = validate_data(valid_data)
    assert result.is_valid
    warnings = warning_messages(valid_data)
    assert any("skill 'Go' is not used" in w for w in warnings)
    assert any("category 'Security' is not used" in w for w in warnings)


def test_project_without_prs_warns(valid_data):
    valid_data["projects"][0]["pr_ids"] = []
    valid_data["projects"][0]["decisions"][0]["pr_ids"] = []
    for pr in valid_data["pull_requests"]:
        pr["project_id"] = None
    assert validate_data(valid_data).is_valid
    assert any("no pull requests" in w for w in warning_messages(valid_data))


def test_metric_without_values_warns(valid_data):
    metric = valid_data["projects"][0]["metrics"][0]
    metric["before"] = metric["after"] = None
    assert validate_data(valid_data).is_valid
    assert any("has no values" in w for w in warning_messages(valid_data))


# ---------- File handling and CLI ----------


def test_missing_file(tmp_path):
    result = validate_file(tmp_path / "nope.json")
    assert not result.is_valid
    assert "file not found" in result.errors[0].message


def test_invalid_json(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{ not json", encoding="utf-8")
    result = validate_file(path)
    assert "invalid JSON" in result.errors[0].message


@pytest.mark.parametrize("break_it, expected_exit", [(False, 0), (True, 1)])
def test_cli_exit_code(tmp_path, valid_data, capsys, break_it, expected_exit):
    if break_it:
        valid_data["projects"][0]["categories"] = ["Nope"]
    path = tmp_path / "experience.json"
    path.write_text(json.dumps(valid_data), encoding="utf-8")
    assert main([str(path)]) == expected_exit
    assert ("✓ Valid" if expected_exit == 0 else "✗ Invalid") in capsys.readouterr().out


# ---------- Exported schema ----------


def test_exported_schema_is_up_to_date():
    assert SCHEMA_PATH.exists(), "run `uv run workstory-export-schema`"
    assert SCHEMA_PATH.read_text(encoding="utf-8") == render_schema(), (
        "extraction/schema.json is stale; run `uv run workstory-export-schema`"
    )


# ---------- Sample dataset ----------

SAMPLE_PATH = SCHEMA_PATH.parents[1] / "examples" / "sample-experience.json"


def test_sample_dataset_is_valid_without_warnings():
    result = validate_file(SAMPLE_PATH)
    assert result.is_valid, [str(i) for i in result.errors]
    assert result.warnings == [], [str(i) for i in result.warnings]
