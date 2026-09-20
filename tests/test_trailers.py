import time

from backend import trailers


def signed(expires: int) -> str:
    return (
        "https://imdb-video.media-imdb.com/vi123456789/clip.mp4"
        f"?Expires={expires}&Signature=abc&Key-Pair-Id=XYZ"
    )


def test_a_fresh_signed_url_is_not_stale() -> None:
    assert trailers.is_stale(signed(int(time.time()) + 86400)) is False


def test_a_url_inside_the_refresh_margin_is_stale() -> None:
    assert trailers.is_stale(signed(int(time.time()) + 60)) is True


def test_an_expired_url_is_stale() -> None:
    assert trailers.is_stale(signed(int(time.time()) - 60)) is True


def test_missing_or_unsigned_urls_are_stale() -> None:
    assert trailers.is_stale(None) is True
    assert trailers.is_stale("") is True
    assert trailers.is_stale("https://example.com/clip.mp4") is True


def test_only_imdb_video_hosts_are_accepted() -> None:
    assert trailers._is_imdb_video("https://imdb-video.media-imdb.com/vi1/a.mp4") is True
    assert trailers._is_imdb_video("http://imdb-video.media-imdb.com/vi1/a.mp4") is False
    assert trailers._is_imdb_video("https://evil.example.com/a.mp4") is False
    assert trailers._is_imdb_video("https://imdb-video.media-imdb.com.evil.com/a.mp4") is False
    assert trailers._is_imdb_video(None) is False


def test_definition_order_puts_the_override_first(monkeypatch) -> None:
    monkeypatch.setenv("REELPICK_TRAILER_DEFINITION", "DEF_720p")

    order = trailers.definition_order()

    assert order[0] == "DEF_720p"
    assert sorted(order) == sorted(trailers.DEFINITION_ORDER)


def test_definition_order_defaults_to_the_lighter_stream(monkeypatch) -> None:
    monkeypatch.delenv("REELPICK_TRAILER_DEFINITION", raising=False)

    assert trailers.definition_order()[0] == "DEF_480p"


def test_a_trailer_is_preferred_over_other_video_types(monkeypatch) -> None:
    monkeypatch.setattr(
        trailers,
        "get_json",
        lambda *a, **k: {
            "d": [
                {
                    "id": "tt2267998",
                    "v": [
                        {"id": "vi1000000001", "l": "TV Spot"},
                        {"id": "vi1000000002", "l": "Trailer #2"},
                    ],
                }
            ]
        },
    )

    assert trailers._best_video_id("tt2267998") == "vi1000000002"


def test_the_first_video_is_used_when_no_trailer_is_labelled(monkeypatch) -> None:
    monkeypatch.setattr(
        trailers,
        "get_json",
        lambda *a, **k: {
            "d": [{"id": "tt2267998", "v": [{"id": "vi1000000001", "l": "Clip"}]}]
        },
    )

    assert trailers._best_video_id("tt2267998") == "vi1000000001"


def test_malformed_ids_never_reach_the_network(monkeypatch) -> None:
    def explode(*args, **kwargs):
        raise AssertionError("network call attempted")

    monkeypatch.setattr(trailers, "get_json", explode)

    assert trailers._best_video_id("not-an-id") is None
    assert trailers._best_video_id(None) is None
    assert trailers.trailer_urls_for(["", None, "nope"]) == {}
