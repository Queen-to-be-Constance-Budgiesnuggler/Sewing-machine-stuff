from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from mcp_server.models import MachineKnowledge

FIXTURES = Path(__file__).parent / "fixtures"


def load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text())


def test_good_knowledge_file_validates():
    data = load_yaml(FIXTURES / "good_manuals" / "test-machine" / "knowledge.yaml")
    mk = MachineKnowledge.model_validate(data)
    assert mk.machine.slug == "test-machine"
    assert len(mk.settings) == 2
    assert mk.settings[1].related_settings == [1]


def test_duplicate_setting_numbers_rejected():
    data = load_yaml(FIXTURES / "bad_manuals" / "test-machine-bad" / "knowledge.yaml")
    with pytest.raises(ValidationError):
        MachineKnowledge.model_validate(data)


def test_bad_slug_format_rejected():
    data = load_yaml(FIXTURES / "good_manuals" / "test-machine" / "knowledge.yaml")
    data["machine"]["slug"] = "Not A Valid Slug!"
    with pytest.raises(ValidationError):
        MachineKnowledge.model_validate(data)


def test_dangling_related_setting_reference_rejected():
    data = load_yaml(FIXTURES / "good_manuals" / "test-machine" / "knowledge.yaml")
    data["settings"][0]["related_settings"] = [999]
    with pytest.raises(ValidationError):
        MachineKnowledge.model_validate(data)


def test_dangling_settings_to_recheck_reference_rejected():
    data = load_yaml(FIXTURES / "good_manuals" / "test-machine" / "knowledge.yaml")
    data["disassembly"][0]["settings_to_recheck"] = [999]
    with pytest.raises(ValidationError):
        MachineKnowledge.model_validate(data)
