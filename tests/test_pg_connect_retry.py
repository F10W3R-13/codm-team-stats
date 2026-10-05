"""db._pg_connect: Postgres 콜드 스타트("starting up")만 재시도, 그 외 에러는 즉시 실패."""
import sys
import types

import pytest

import db


def _fake_psycopg2(monkeypatch, errors):
    class OperationalError(Exception):
        pass

    calls = []

    def connect(_url):
        calls.append(1)
        if errors:
            raise OperationalError(errors.pop(0))
        return "conn"

    monkeypatch.setitem(sys.modules, "psycopg2",
                        types.SimpleNamespace(connect=connect, OperationalError=OperationalError))
    return calls, OperationalError


def test_retries_while_starting_up(monkeypatch):
    calls, _ = _fake_psycopg2(monkeypatch, ["FATAL: the database system is starting up"] * 2)
    assert db._pg_connect(delay=0) == "conn"
    assert len(calls) == 3


def test_other_errors_fail_fast(monkeypatch):
    calls, err = _fake_psycopg2(monkeypatch, ["password authentication failed"])
    with pytest.raises(err):
        db._pg_connect(delay=0)
    assert len(calls) == 1


def test_gives_up_after_retries(monkeypatch):
    calls, err = _fake_psycopg2(monkeypatch, ["the database system is starting up"] * 9)
    with pytest.raises(err):
        db._pg_connect(retries=3, delay=0)
    assert len(calls) == 3
