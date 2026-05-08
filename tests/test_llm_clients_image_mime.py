from __future__ import annotations

from clogem.llm_clients import _guess_mime_type_for_image_path


def test_guess_mime_type_for_jpg_image() -> None:
    assert _guess_mime_type_for_image_path("photo.jpg") == "image/jpeg"


def test_guess_mime_type_for_webp_image() -> None:
    assert _guess_mime_type_for_image_path("frame.webp") == "image/webp"


def test_guess_mime_type_falls_back_to_png_for_unknown_extension() -> None:
    assert _guess_mime_type_for_image_path("blob.unknownext") == "image/png"
