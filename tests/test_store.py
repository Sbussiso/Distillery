from __future__ import annotations

import pytest

from distillery.schemas import Sample
from distillery.store import StoreError, store


@pytest.mark.parametrize("bad", ["..", ".", "a/b", "", "../x", "a\\b"])
def test_invalid_session_ids_are_rejected(bad, datasets_root):
    with pytest.raises(StoreError):
        store.delete_session(bad)
    with pytest.raises(StoreError):
        store.session_dir(bad)
    assert datasets_root.parent.exists()


def test_reads_do_not_create_directories(datasets_root):
    assert list(store.iter_samples("missing")) == []
    assert store.count_samples("missing") == 0
    assert store.get_samples("missing", 0, 10) == (0, [])
    with pytest.raises(StoreError):
        store.load_session("missing")
    with pytest.raises(StoreError):
        store.export_path("missing", "raw")
    assert not (datasets_root / "missing").exists()


def test_get_samples_pages(datasets_root):
    for i in range(7):
        store.append_sample("s1", Sample(
            question=f"q{i}", answer="a", thinking="", score=9, passed=True,
            judge_reasoning="ok", teacher_model="t", judge_model="j",
            topics=[], difficulty="any", timestamp="now",
        ))
    total, page = store.get_samples("s1", 5, 10)
    assert total == 7
    assert [s.question for s in page] == ["q5", "q6"]
    assert store.count_samples("s1") == 7
