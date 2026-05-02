import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from session import Session
from tool_dispatcher import execute_tool_direct
from prompt_builder import _compact_history

@pytest.fixture
def mock_session():
    return Session(user_id=1, message_history=[])

@pytest.mark.anyio
async def test_execute_tool_direct_valid_json():
    with patch("tools.registry.TOOL_REGISTRY") as mock_registry:
        mock_target = AsyncMock(return_value="tool output")
        mock_registry.get.return_value = mock_target
        
        res = await execute_tool_direct(
            func_name="dummy_tool",
            func_args='{"arg1": "value"}',
            user_id=1,
        )
        assert res == "tool output"
        mock_target.assert_called_once()

@pytest.mark.anyio
async def test_execute_tool_direct_invalid_json():
    res = await execute_tool_direct(
        func_name="dummy_tool",
        func_args='{invalid json}',
        user_id=1,
    )
    assert "Error: Arguments for dummy_tool must be a JSON object" in res

@pytest.mark.anyio
async def test_compact_history(mock_session):
    mock_router = MagicMock()
    mock_router.chat_completions = AsyncMock(return_value=MagicMock(
        choices=[MagicMock(message=MagicMock(content="compacted summary"))]
    ))
    
    # Needs more than 10 messages to trigger compaction
    mock_session.message_history = [{"role": "system", "content": "mock system"}] + [
        {"role": "user", "content": f"msg {i}"} for i in range(11)
    ]
    
    await _compact_history(mock_session, mock_router)
    
    # First message should be system, second should be the compacted summary
    assert mock_session.message_history[0]["role"] == "system"
    assert mock_session.message_history[1]["role"] == "assistant"
    assert "compacted summary" in mock_session.message_history[1]["content"]
    assert len(mock_session.message_history) == 8
