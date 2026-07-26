import base64

from PIL import Image

from npv_build.gui_logic.thumbs import thumbnail_b64


def _img(path, size=(512, 512)):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, "red").save(path, "JPEG")


def test_thumbnail_generated_cached_and_decodable(tmp_path):
    _img(tmp_path / "imgs" / "foo.jpg")
    out = thumbnail_b64(
        "/images/clothes/foo.jpg",
        str(tmp_path / "imgs"),
        tmp_path / "cache",
    )
    assert out is not None
    raw = base64.b64decode(out)
    assert raw[:2] == b"\xff\xd8"
    thumbs = list((tmp_path / "cache" / "thumbs").iterdir())
    assert len(thumbs) == 1
    with Image.open(thumbs[0]) as thumb:
        assert max(thumb.size) <= 256
    mtime = thumbs[0].stat().st_mtime_ns
    assert (
        thumbnail_b64(
            "/images/clothes/foo.jpg",
            str(tmp_path / "imgs"),
            tmp_path / "cache",
        )
        == out
    )
    assert thumbs[0].stat().st_mtime_ns == mtime


def test_source_can_be_resolved_from_parent_of_images_layout(tmp_path):
    _img(tmp_path / "static" / "images" / "clothes" / "foo.jpg")
    assert (
        thumbnail_b64(
            "/images/clothes/foo.jpg",
            str(tmp_path / "static"),
            tmp_path / "cache",
        )
        is not None
    )


def test_missing_dir_file_or_invalid_image_degrades_to_none(tmp_path):
    assert thumbnail_b64("/images/clothes/foo.jpg", None, tmp_path) is None
    assert (
        thumbnail_b64(
            "/images/clothes/foo.jpg",
            str(tmp_path / "nope"),
            tmp_path,
        )
        is None
    )
    (tmp_path / "imgs").mkdir()
    assert (
        thumbnail_b64(
            "/images/clothes/ghost.jpg",
            str(tmp_path / "imgs"),
            tmp_path,
        )
        is None
    )
    (tmp_path / "imgs" / "bad.jpg").write_text("not an image")
    assert (
        thumbnail_b64(
            "/images/clothes/bad.jpg",
            str(tmp_path / "imgs"),
            tmp_path,
        )
        is None
    )
