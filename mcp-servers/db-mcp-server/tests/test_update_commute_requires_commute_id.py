import pytest
import json

from server import RepositoryContainer
from tests.handler_test_utils import HandlerTestHelper
from tools.travel_tools import _update_commute_tool


def test_update_commute_tool_schema_requires_commute_id():
    tool = _update_commute_tool()
    required = tool.inputSchema.get("required", [])
    assert required == ["commute_id"], f"Unexpected required fields: {required}"


class TestUpdateCommuteHandler:
    @pytest.mark.asyncio
    async def test_update_commute_requires_commute_id(self, db_connection):
        repos = RepositoryContainer(db_connection)
        helper = HandlerTestHelper(db_connection, repos)

        result = await helper.call_tool("update_commute", {"event_id": "not-used"})
        payload = json.loads(result)

        assert "error" in payload
        assert "commute_id" in payload["error"].lower()
