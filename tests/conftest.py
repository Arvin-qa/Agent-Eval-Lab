"""默认 pytest 全程拦截网络：offline 评测不得发起任何真实连接（AC02）。"""
import socket

import pytest


@pytest.fixture(autouse=True)
def block_network(monkeypatch):
    def _refuse(*args, **kwargs):
        raise AssertionError("offline 测试试图发起网络连接，被 conftest 拦截")

    monkeypatch.setattr(socket.socket, "connect", _refuse)
    monkeypatch.setattr(socket, "create_connection", _refuse)
