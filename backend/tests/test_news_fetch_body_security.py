import socket
import os
import sys

import httpx
import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.join(os.getcwd(), "backend"))

from api import news_routes


class _FakeResponse:
    def __init__(self, url, status_code=200, headers=None, text=""):
        self.url = url
        self.status_code = status_code
        self.headers = headers or {}
        self.text = text


class _FakeAsyncClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def get(self, url):
        self.calls.append(url)
        return self.responses.pop(0)


@pytest.mark.asyncio
async def test_fetch_article_body_rejects_private_url_before_request(monkeypatch):
    client = _FakeAsyncClient([])
    monkeypatch.setattr(httpx, "AsyncClient", lambda **_kwargs: client)

    with pytest.raises(HTTPException) as exc:
        await news_routes.fetch_article_body("http://127.0.0.1:8000/admin")

    assert exc.value.status_code == 400
    assert client.calls == []


@pytest.mark.asyncio
async def test_fetch_article_body_rejects_redirect_to_private_url(monkeypatch):
    def fake_getaddrinfo(hostname, *_args, **_kwargs):
        assert hostname == "example.com"
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

    client = _FakeAsyncClient([
        _FakeResponse(
            "https://example.com/news",
            status_code=302,
            headers={"location": "http://127.0.0.1/admin"},
        )
    ])
    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    monkeypatch.setattr(httpx, "AsyncClient", lambda **_kwargs: client)

    with pytest.raises(HTTPException) as exc:
        await news_routes.fetch_article_body("https://example.com/news")

    assert exc.value.status_code == 400
    assert client.calls == ["https://example.com/news"]


@pytest.mark.asyncio
async def test_fetch_article_body_allows_public_article_url(monkeypatch):
    def fake_getaddrinfo(hostname, *_args, **_kwargs):
        assert hostname == "example.com"
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

    client = _FakeAsyncClient([
        _FakeResponse(
            "https://example.com/news",
            status_code=200,
            text="<html><p>삼성전자 실적 개선과 수급 변화가 시장에서 주목받고 있다는 기사 본문입니다.</p></html>",
        )
    ])
    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    monkeypatch.setattr(httpx, "AsyncClient", lambda **_kwargs: client)

    result = await news_routes.fetch_article_body("https://example.com/news")

    assert result["body"] == "삼성전자 실적 개선과 수급 변화가 시장에서 주목받고 있다는 기사 본문입니다."
    assert client.calls == ["https://example.com/news"]
