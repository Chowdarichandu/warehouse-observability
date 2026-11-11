import sys
import types

from obs.integrations import warehouse


class FakeSnowflakeCursor:
    description = [("TABLE_NAME",), ("ROW_COUNT",)]

    def __init__(self):
        self.calls = []

    def execute(self, query, params):
        self.calls.append((query, params))

    def fetchall(self):
        return [("orders", 12)]


class FakeSnowflakeConnection:
    def __init__(self):
        self.cursor_instance = FakeSnowflakeCursor()
        self.closed = False

    def cursor(self):
        return self.cursor_instance

    def close(self):
        self.closed = True


def test_snowflake_adapter_returns_dict_rows_and_closes_connection():
    connection = FakeSnowflakeConnection()
    adapter = warehouse._SnowflakeConnection(connection)
    with adapter as active:
        result = active.execute("SELECT %s", ("orders",))
        assert result.fetchall() == [{"table_name": "orders", "row_count": 12}]
    assert connection.closed
    assert connection.cursor_instance.calls == [("SELECT %s", ("orders",))]


def test_bigquery_adapter_uses_bound_query_parameters(monkeypatch):
    class ScalarQueryParameter:
        def __init__(self, name, kind, value):
            self.name, self.kind, self.value = name, kind, value

    class QueryJobConfig:
        def __init__(self, **kwargs):
            self.query_parameters = kwargs["query_parameters"]
            self.use_query_cache = kwargs["use_query_cache"]

    class Job:
        def result(self):
            return [{"table_name": "orders"}]

    class Client:
        def __init__(self, **kwargs):
            self.calls = []

        def query(self, query, job_config):
            self.calls.append((query, job_config))
            return Job()

    fake_bigquery = types.SimpleNamespace(
        ScalarQueryParameter=ScalarQueryParameter,
        QueryJobConfig=QueryJobConfig,
    )
    fake_google = types.ModuleType("google")
    fake_cloud = types.ModuleType("google.cloud")
    fake_cloud.bigquery = fake_bigquery
    monkeypatch.setitem(sys.modules, "google", fake_google)
    monkeypatch.setitem(sys.modules, "google.cloud", fake_cloud)
    monkeypatch.setitem(sys.modules, "google.cloud.bigquery", fake_bigquery)

    client = Client()
    adapter = warehouse._BigQueryConnection(client)
    result = adapter.execute(
        'SELECT * FROM "project.dataset.INFORMATION_SCHEMA.COLUMNS" WHERE table_schema=%s',
        ("orders",),
    )
    assert result.fetchall() == [{"table_name": "orders"}]
    query, config = client.calls[0]
    assert "@p0" in query and '"' not in query
    assert config.query_parameters[0].kind == "STRING"
