import pytest

from graph import supervisor
from graph.supervisor import CHECKPOINT_TTL, expire_untracked_checkpoints


class FakeRedis:
    def __init__(self, keys: dict[str, int]):
        self.ttls = dict(keys)
        self.expired: dict[str, int] = {}

    async def scan_iter(self, match=None, count=None):
        for key in list(self.ttls):
            yield key

    async def ttl(self, key):
        return self.ttls[key]

    async def expire(self, key, seconds):
        self.expired[key] = seconds
        self.ttls[key] = seconds


@pytest.fixture
def redis(monkeypatch):
    def serve(keys: dict[str, int]):
        client = FakeRedis(keys)
        graph = type("Graph", (), {"checkpointer": type("Saver", (), {"_redis": client})})

        async def fake_get_graph():
            return graph

        monkeypatch.setattr(supervisor, "get_graph", fake_get_graph)
        return client

    return serve


def test_the_saver_is_configured_to_expire_and_refresh():
    assert CHECKPOINT_TTL["default_ttl"] == 7 * 24 * 60
    # A run waiting on an approval keeps being read; without this it would expire mid-wait.
    assert CHECKPOINT_TTL["refresh_on_read"] is True


async def test_keys_without_an_expiry_get_one(redis):
    client = redis({"checkpoint:a": -1, "checkpoint_write:b": -1})
    assert await expire_untracked_checkpoints() == 2
    assert client.expired == {"checkpoint:a": 7 * 24 * 3600, "checkpoint_write:b": 7 * 24 * 3600}


async def test_keys_that_already_expire_are_left_alone(redis):
    client = redis({"checkpoint:a": 3600})
    assert await expire_untracked_checkpoints() == 0
    assert client.expired == {}


async def test_the_window_can_be_overridden(redis):
    client = redis({"checkpoint:a": -1})
    await expire_untracked_checkpoints(ttl_minutes=30)
    assert client.expired == {"checkpoint:a": 1800}
