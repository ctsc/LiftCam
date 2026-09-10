import psycopg
import pytest

from liftcam.core.settings import get_settings


def test_can_connect_to_configured_database() -> None:
    """Proves the compose Postgres and settings URL line up. Skips when Postgres is down."""
    try:
        conn = psycopg.connect(get_settings().database_url, connect_timeout=3)
    except psycopg.OperationalError as exc:
        pytest.skip(f"Postgres not reachable: {exc}")

    with conn, conn.cursor() as cur:
        cur.execute("SELECT 1")
        assert cur.fetchone() == (1,)
