from PIL import Image

from npv_build.core.image_diff import compare, rms_diff


def _png(path, color, size=(32, 32)):
    Image.new("RGBA", size, color).save(path)
    return path


def test_identical_images_match(tmp_path):
    a = _png(tmp_path / "a.png", (120, 30, 200, 255))
    b = _png(tmp_path / "b.png", (120, 30, 200, 255))
    assert rms_diff(a, b) == 0.0
    assert compare(a, b) == {"match": True, "rms": 0.0, "reason": ""}


def test_small_noise_within_threshold(tmp_path):
    a = _png(tmp_path / "a.png", (100, 100, 100, 255))
    b = _png(tmp_path / "b.png", (102, 100, 99, 255))
    result = compare(a, b, threshold=3.0)
    assert result["match"] is True and 0 < result["rms"] < 3.0


def test_wrong_color_fails(tmp_path):
    a = _png(tmp_path / "a.png", (10, 10, 10, 255))
    b = _png(tmp_path / "b.png", (200, 200, 200, 255))
    result = compare(a, b, threshold=3.0)
    assert result["match"] is False and result["reason"].startswith("rms ")


def test_dimension_mismatch_fails(tmp_path):
    a = _png(tmp_path / "a.png", (0, 0, 0, 255), size=(32, 32))
    b = _png(tmp_path / "b.png", (0, 0, 0, 255), size=(16, 16))
    assert rms_diff(a, b) == float("inf")
    assert compare(a, b) == {"match": False, "rms": float("inf"), "reason": "dimension mismatch"}
