from pathlib import Path


def test_startup_validator_exceptions_fail_closed():
    source = (Path(__file__).resolve().parents[1] / 'project_guardian' / '__main__.py').read_text(encoding='utf-8')
    assert 'refusing unvalidated startup' in source
    assert 'Configuration validation failed unexpectedly' in source
    assert 'Configuration validation skipped' not in source
