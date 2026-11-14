"""Shared fixtures of the agent-platform suites (REQ-AGT-001..008; DRAFT, PENDING owner approval).

Every test here runs OFFLINE: the autouse guard below refuses any socket connection to a non-loopback
address and removes ANTHROPIC_API_KEY, so a test that would reach a model provider, a cloud service or
the internet fails instead of silently spending money or sending data. Loopback stays open because the
asyncio event loop on Windows builds its self-pipe with a local socket pair.

Run (light load, one file at a time, no credentials):
    GOOGLE_APPLICATION_CREDENTIALS=<missing file> CLOUDSDK_CONFIG=<empty dir> \
    GOOGLE_CLOUD_PROJECT=mstool-offline-tests python -m pytest tests/agent_platform/<file> -q
"""
import ipaddress
import socket
import pytest

_LOOPBACK_NAMES = {"localhost", ""}


def _is_loopback(address) -> bool:
    host = address[0] if isinstance(address, tuple) and address else address
    if isinstance(host, (bytes, bytearray)):
        host = host.decode("ascii", "ignore")
    if not isinstance(host, str):
        return False
    if host in _LOOPBACK_NAMES:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


class NetworkRefused(RuntimeError):
    """A test of the agent platform tried to reach the network."""


@pytest.fixture(autouse=True)
def _offline_only(monkeypatch):
    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex

    def connect(self, address):
        if not _is_loopback(address):
            raise NetworkRefused(f"agent-platform tests are offline; refused a connection to {address!r}")
        return real_connect(self, address)

    def connect_ex(self, address):
        if not _is_loopback(address):
            raise NetworkRefused(f"agent-platform tests are offline; refused a connection to {address!r}")
        return real_connect_ex(self, address)

    def create_connection(address, *args, **kwargs):
        raise NetworkRefused(f"agent-platform tests are offline; refused a connection to {address!r}")

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket.socket, "connect_ex", connect_ex)
    monkeypatch.setattr(socket, "create_connection", create_connection)
    for key in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_MODEL"):
        monkeypatch.delenv(key, raising=False)
    yield


from tests.agent_platform._fixtures import FIXED_NOW, make_registry_data  # noqa: E402


@pytest.fixture
def audit_events():
    return []


@pytest.fixture
def switches():
    from app.agent_platform.registry import InMemoryKillSwitches
    return InMemoryKillSwitches({"test-agent": True, "other-agent": True, "pending-agent": True})


@pytest.fixture
def ledger():
    from app.agent_platform.registry import InMemoryCostLedger
    return InMemoryCostLedger()


@pytest.fixture
def registry(switches, ledger, audit_events):
    from app.agent_platform.registry import AgentRegistry
    return AgentRegistry(make_registry_data(), switches=switches, ledger=ledger,
                         audit=audit_events.append, clock=lambda: FIXED_NOW)
