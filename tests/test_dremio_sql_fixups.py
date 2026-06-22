import pytest

from adl_automated_delivery_pipeline.workflows.adl_automated_delivery_pipeline import (
    _fix_reserved_keywords,
)

pytestmark = pytest.mark.unit


def test_bare_reserved_in_select_list_is_quoted():
    assert _fix_reserved_keywords("SELECT a, value, b FROM t") == 'SELECT a, "value", b FROM t'


def test_bare_reserved_as_last_select_item():
    assert _fix_reserved_keywords("SELECT a, value FROM t") == 'SELECT a, "value" FROM t'


def test_bare_reserved_as_only_select_item():
    assert _fix_reserved_keywords("SELECT value FROM t") == 'SELECT "value" FROM t'


def test_bare_reserved_multiline_select_item():
    sql = "SELECT\n  event_perfno_i,\n  value,\n  ac_typ\nFROM t"
    assert _fix_reserved_keywords(sql) == 'SELECT\n  event_perfno_i,\n  "value",\n  ac_typ\nFROM t'


def test_reserved_in_function_arg_is_quoted():
    assert _fix_reserved_keywords("SELECT COUNT(value) FROM t") == 'SELECT COUNT("value") FROM t'


def test_date_literal_not_quoted():
    sql = "SELECT DATE_ADD(DATE '1971-12-31', CAST(ref_date AS BIGINT)) AS ref_date FROM t"
    out = _fix_reserved_keywords(sql)
    assert '"DATE"' not in out
    assert "DATE '1971-12-31'" in out


def test_extract_field_not_quoted():
    out = _fix_reserved_keywords("SELECT EXTRACT(YEAR FROM ref_date) AS yr FROM t")
    assert '"YEAR"' not in out


def test_existing_as_and_dot_patterns_still_quoted():
    assert _fix_reserved_keywords("SELECT t.value FROM t") == 'SELECT t."value" FROM t'
    assert _fix_reserved_keywords("SELECT x AS value FROM t") == 'SELECT x AS "value" FROM t'
