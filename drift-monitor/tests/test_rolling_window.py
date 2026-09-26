"""
Unit tests - rolling live window (task.md 15.4).

    N images  -> exactly one full window
    N + S     -> next expected window
    incomplete window -> no false verdict
"""

import numpy as np
import pytest

from src.rolling_window import RollingWindow, RollingWindowError, feed_stream


def test_n_images_exactly_one_window():
    window = RollingWindow(window_size=10, step_size=5)
    embs = np.arange(10 * 4, dtype=np.float64).reshape(10, 4)
    windows = list(feed_stream(window, embs))
    assert len(windows) == 1
    seq_idx, win = windows[0]
    assert seq_idx == 0
    assert len(win) == 10
    np.testing.assert_array_equal(win.embeddings(), embs)


def test_n_plus_s_gives_two_windows():
    window = RollingWindow(window_size=10, step_size=5)
    embs = np.arange(15 * 4, dtype=np.float64).reshape(15, 4)
    windows = list(feed_stream(window, embs))
    assert len(windows) == 2
    # Second window holds the last 10 of the 15 images (slid by 5).
    np.testing.assert_array_equal(windows[1][1].embeddings(), embs[5:])


def test_incomplete_window_yields_nothing():
    window = RollingWindow(window_size=10, step_size=5)
    embs = np.zeros((9, 4))
    assert list(feed_stream(window, embs)) == []
    assert not window.is_comparable()


def test_minimum_samples_gates_verdict():
    window = RollingWindow(window_size=10, step_size=5, minimum_samples=10)
    for i in range(9):
        window.add(np.full(4, i, dtype=np.float64))
        assert not window.is_comparable()
    window.add(np.full(4, 9, dtype=np.float64))
    assert window.is_comparable()


def test_buffer_rotates_not_grows():
    window = RollingWindow(window_size=8, step_size=4)
    rng = np.random.default_rng(0)
    for i in range(500):
        window.add(rng.normal(0, 1, 6))
        assert len(window._buffer) <= 8


def test_window_id_deterministic_from_contents():
    w1 = RollingWindow(window_size=6, step_size=3)
    w2 = RollingWindow(window_size=6, step_size=3)
    embs = np.arange(6 * 3, dtype=np.float64).reshape(6, 3)
    wins1 = list(feed_stream(w1, embs))
    wins2 = list(feed_stream(w2, embs))
    assert wins1[0][1].window_id(0) == wins2[0][1].window_id(0)
    # Same stream -> same window IDs.
    assert [w.window_id(i) for i, w in wins1] == [w.window_id(i) for i, w in wins2]


def test_window_id_changes_with_content():
    w = RollingWindow(window_size=6, step_size=3)
    a = list(feed_stream(w, np.ones((6, 3))))
    id_a = a[0][1].window_id(0)
    w2 = RollingWindow(window_size=6, step_size=3)
    b = list(feed_stream(w2, np.ones((6, 3)) * 2))
    id_b = b[0][1].window_id(0)
    assert id_a != id_b


def test_window_metadata_recorded():
    window = RollingWindow(window_size=4, step_size=2)
    meta = [{"image_id": f"img{i}", "source_id": "camA", "timestamp": f"2026-01-0{i+1}T00:00:00Z"}
            for i in range(4)]
    embs = np.ones((4, 5))
    windows = list(feed_stream(window, embs, meta))
    desc = windows[0][1].describe(0, "reference-v1")
    assert desc["window_id"].startswith("window-000000-")
    assert desc["image_count"] == 4
    assert desc["first_timestamp"] == "2026-01-01T00:00:00Z"
    assert desc["last_timestamp"] == "2026-01-04T00:00:00Z"
    assert desc["source_ids"] == ["camA"]
    assert desc["image_ids"] == ["img0", "img1", "img2", "img3"]
    assert desc["reference_id"] == "reference-v1"
    assert desc["embedding_digest"]


def test_invalid_config_rejected():
    with pytest.raises(RollingWindowError):
        RollingWindow(window_size=1, step_size=5)
    with pytest.raises(RollingWindowError):
        RollingWindow(window_size=10, step_size=0)
    with pytest.raises(RollingWindowError):
        RollingWindow(window_size=10, step_size=5, minimum_samples=11)


def test_add_validates_shape():
    window = RollingWindow(window_size=4, step_size=2)
    with pytest.raises(RollingWindowError):
        window.add(np.zeros((2, 2)))  # 2-D, must be 1-D
