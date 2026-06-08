"""Tests for news provider query construction."""

import os
import sys

sys.path.insert(0, os.path.join(os.getcwd(), "backend"))

from news.providers.google_news import _build_search_queries


def test_google_news_queries_use_company_news_terms_not_stock_only_terms():
    queries = _build_search_queries("현대자동차")

    assert queries[0] == "현대자동차 OR 현대차"
    assert "현대자동차 주식" not in queries


def test_google_news_queries_keep_single_name_when_no_alias_rule_applies():
    assert _build_search_queries("삼성전자") == ["삼성전자"]
