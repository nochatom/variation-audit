"""Lightweight fakes so worker/service logic can be tested without a real DB.

These stand in for a SQLAlchemy Session: they record `add`/`commit`/`flush`
and return pre-queued results from `execute`, which is enough to exercise the
pure logic in job_worker and services.jobs without Postgres.
"""
from __future__ import annotations


class FakeScalars:
    def __init__(self, items):
        self._items = items

    def all(self):
        return list(self._items)


class FakeResult:
    """Mimics the bits of a SQLAlchemy Result the code uses."""

    def __init__(self, scalar=None, scalars=None, rows=None):
        self._scalar = scalar
        self._scalars = scalars or []
        self._rows = rows or []          # for .all() (e.g. multi-column selects)

    def scalar_one_or_none(self):
        return self._scalar

    def scalar_one(self):
        # Deliberately returns only what the test supplied. It must NOT fall
        # back to len(self._scalars): a COUNT query is now the thing under
        # test, and inferring its result from however many rows happen to be
        # staged would let a query with a wrong or missing WHERE clause pass.
        # Tests that exercise a count pass `scalar=N` explicitly.
        return self._scalar

    def scalars(self):
        return FakeScalars(self._scalars)

    def all(self):
        return list(self._rows)


class FakeSession:
    """Records writes; returns queued results for successive execute() calls."""

    def __init__(self, results=None, get_obj=None):
        self.added: list = []
        self.deleted: list = []
        self.commits = 0
        self.flushes = 0
        self.refreshes = 0
        self._results = list(results or [])
        self._get_obj = get_obj            # returned by session.get(...)

    # -- query side --------------------------------------------------------
    def execute(self, _stmt):
        if self._results:
            return self._results.pop(0)
        return FakeResult()

    def get(self, _cls, _pk):
        return self._get_obj

    # -- write side --------------------------------------------------------
    def add(self, obj):
        self.added.append(obj)

    def delete(self, obj):
        self.deleted.append(obj)

    def flush(self):
        self.flushes += 1

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass

    def refresh(self, _obj):
        self.refreshes += 1

    # -- helpers for assertions -------------------------------------------
    def added_of(self, cls):
        return [o for o in self.added if isinstance(o, cls)]
