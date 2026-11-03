"""Real official pages can include HTML boolean attributes with no value."""
from app.ingestion import normalize_html


def test_boolean_id_does_not_abort_official_source_capture():
    assert normalize_html('<div id><p>Navigation</p></div><main id><h1>OPT guidance</h1><p>Check official requirements.</p></main>') == 'OPT guidance\nCheck official requirements.'
