import pytest
from tools.database_ops import add_worker_task, get_worker_status, update_worker_status, _conn_ctx

@pytest.fixture
def cleanup_task():
    with _conn_ctx() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM background_tasks WHERE task_id = 'test_w_1'")
    yield
    with _conn_ctx() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM background_tasks WHERE task_id = 'test_w_1'")

def test_worker_lifecycle(cleanup_task):
    task_id = "test_w_1"
    add_worker_task(task_id, 123, "Backend", "Fix DB")
    status = get_worker_status(task_id)
    assert status["status"] == "running"
    
    update_worker_status(task_id, "needs_help", "I don't understand the schema")
    status = get_worker_status(task_id)
    assert status["status"] == "needs_help"
    assert status["result"] == "I don't understand the schema"
