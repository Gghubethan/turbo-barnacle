"""Run with: python -m pytest lens-kb/tools -q"""
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location("validate", Path(__file__).with_name("validate.py"))
validate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(validate)


def test_knowledge_base_is_consistent(capsys):
    assert validate.main([]) == 0, capsys.readouterr().out


def test_tagged_ids_rejects_unknown_evidence_group():
    import pytest
    with pytest.raises(ValueError):
        validate.tagged_ids({"D": ["FUNC_001"]})
    assert validate.tagged_ids({"A": ["FUNC_001"], "B": ["FUNC_002"]}) == ["FUNC_001", "FUNC_002"]
    assert validate.tagged_ids("资料未提供") == []
