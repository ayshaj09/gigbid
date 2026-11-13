import logging

import pytest

logging.getLogger("mcp").setLevel(logging.WARNING)


@pytest.fixture
def cfg():
    from agent.config import load_config

    return load_config({"models": {"profile": "offline"}})
