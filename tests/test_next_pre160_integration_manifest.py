from pathlib import Path


def test_next_pre160_manifest_keeps_setup_deferred_and_real_trading_off():
    text=Path('NEXT_PRE160_INTEGRATION.md').read_text(encoding='utf-8')
    assert '|71|' in text and '|90|' in text
    assert 'No Windows version bump' in text
    assert 'REAL_TRADING=false' in text
    assert 'Candidate 1.6.0 remains blocked' in text
