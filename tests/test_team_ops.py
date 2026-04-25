import pytest
from tools.database_ops import add_worker_task, get_worker_status, update_worker_status

def test_worker_lifecycle():
    task_id = "test_w_1"
    add_worker_task(task_id, 123, "Backend", "Fix DB")
    status = get_worker_status(task_id)
    assert status["status"] == "running"
    
    update_worker_status(task_id, "needs_help", "I don't understand the schema")
    status = get_worker_status(task_id)
    assert status["status"] == "needs_help"
    assert status["result"] == "I don't understand the schema"
