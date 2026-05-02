# debug only; remove after
import pytest

@pytest.hookimpl(tryfirst=True)
def pytest_runtest_setup(item):
    if 'test_registry_routable' in str(item.nodeid) and 'ghost' in str(item.nodeid):
        from utils.db import registry
        print(f'[ROUTABLE_DBG] before={item.nodeid} cache_stamp={registry._cache["stamp"]} rows_in_cache={len(registry._cache["rows"])} disabled_prov={registry._runtime_disabled_provider!r}')
        # Force a fresh raw DB read to see what's there
        try:
            from utils.db._connection import get_connection
            conn = get_connection()
            rows = conn.execute("SELECT name, tier, enabled FROM agents WHERE LOWER(name)='ghost'").fetchall()
            print(f'[ROUTABLE_DBG] db_ghost_rows={[dict(r) for r in rows] if rows and hasattr(rows[0],"keys") else list(rows)}')
            conn.close()
        except Exception as e:
            print(f'[ROUTABLE_DBG] db_query_failed: {e!r}')
