import pytest


class FakeMappings:
    def __init__(self, rows: list[dict]):
        self._rows = rows
        self.fetchmany_calls: list[int] = []

    def fetchmany(self, size: int | None = None) -> list[dict]:
        if size is not None:
            self.fetchmany_calls.append(size)
            return self._rows[:size]
        return self._rows


class FakeResult:
    def __init__(self, rows: list[dict]):
        self._mappings = FakeMappings(rows)

    def mappings(self) -> FakeMappings:
        return self._mappings


class FakeConnection:
    def __init__(
        self,
        rows: list[dict] | None = None,
        exc_to_raise: Exception | None = None,
    ):
        self.rows = rows if rows is not None else []
        self.exc_to_raise = exc_to_raise
        self.executed_sqls: list[str] = []

    def exec_driver_sql(self, statement: str) -> FakeResult:
        self.executed_sqls.append(statement)
        if self.exc_to_raise:
            raise self.exc_to_raise
        return FakeResult(self.rows)


class FakeSession:
    def __init__(
        self,
        rows: list[dict] | None = None,
        exc_to_raise: Exception | None = None,
    ):
        self.connection_called = False
        self.fake_connection = FakeConnection(rows=rows, exc_to_raise=exc_to_raise)

    def connection(self) -> FakeConnection:
        self.connection_called = True
        return self.fake_connection


@pytest.fixture
def fake_session_factory():
    """Fixture providing a factory function to create custom FakeSession instances."""

    def _create(
        rows: list[dict] | None = None, exc_to_raise: Exception | None = None
    ) -> FakeSession:
        return FakeSession(rows=rows, exc_to_raise=exc_to_raise)

    return _create
