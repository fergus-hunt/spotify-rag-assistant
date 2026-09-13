import pytest

from src.agent_tools import run_structured_query


def test_validate_sql_runs_before_connecting(fake_session_factory):
    session = fake_session_factory()
    invalid_sql = "SELECT * FROM raw_table"

    with pytest.raises(ValueError, match="query only v_listening_history"):
        run_structured_query(invalid_sql, session)

    assert not session.connection_called


def test_statement_timeout_configuration(fake_session_factory):
    session = fake_session_factory()
    sql = "SELECT * FROM v_listening_history"

    run_structured_query(sql, session, timeout_ms=5000)
    expected_timeout = "SET LOCAL statement_timeout = '5000ms'"
    assert session.fake_connection.executed_sqls[0] == expected_timeout

    custom_session = fake_session_factory()
    run_structured_query(sql, custom_session, timeout_ms=2500)
    expected_custom_timeout = "SET LOCAL statement_timeout = '2500ms'"
    assert custom_session.fake_connection.executed_sqls[0] == expected_custom_timeout


def test_transaction_read_only_configuration(fake_session_factory):
    session = fake_session_factory()
    sql = "SELECT * FROM v_listening_history"

    run_structured_query(sql, session)
    assert (
        session.fake_connection.executed_sqls[1]
        == "SET LOCAL default_transaction_read_only = ON"
    )


def test_percent_wildcard_escaping(fake_session_factory):
    session = fake_session_factory()
    sql = "SELECT * FROM v_listening_history WHERE track_title LIKE '%rock%'"

    run_structured_query(sql, session)
    executed = session.fake_connection.executed_sqls[2]
    expected_sql = "SELECT * FROM v_listening_history WHERE track_title LIKE '%%rock%%'"
    assert executed == expected_sql


def test_max_rows_limiting(fake_session_factory):
    sample_rows = [
        {"id": 1, "title": "Track 1"},
        {"id": 2, "title": "Track 2"},
        {"id": 3, "title": "Track 3"},
        {"id": 4, "title": "Track 4"},
    ]
    session = fake_session_factory(rows=sample_rows)
    sql = "SELECT * FROM v_listening_history"

    results = run_structured_query(sql, session, max_rows=2)

    assert len(results) == 2
    assert results == [
        {"id": 1, "title": "Track 1"},
        {"id": 2, "title": "Track 2"},
    ]


def test_return_format_is_list_of_dicts(fake_session_factory):
    sample_rows = [
        {"track_title": "Song A", "play_count": 10},
        {"track_title": "Song B", "play_count": 5},
    ]
    session = fake_session_factory(rows=sample_rows)
    sql = "SELECT track_title, COUNT(*) FROM v_listening_history GROUP BY track_title"

    result = run_structured_query(sql, session)

    assert isinstance(result, list)
    assert all(isinstance(row, dict) for row in result)
    assert result == sample_rows


def test_exception_propagation(fake_session_factory):
    db_error = RuntimeError("Database connection failed")
    session = fake_session_factory(exc_to_raise=db_error)
    sql = "SELECT * FROM v_listening_history"

    with pytest.raises(RuntimeError, match="Database connection failed"):
        run_structured_query(sql, session)
