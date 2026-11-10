import boilerplate
from data_access import Article

FURNITURE = "Share your Subscriber Article You have 5 articles to share every month. Send this story to a friend! Loading please wait"


def art(i, domain, lead):
    return Article(i, "u", domain, f"t{i}", lead)


def test_prefix_key_normalises_and_needs_length():
    assert boilerplate.prefix_key("  Hello   WORLD  ", 5) == "hello"
    assert boilerplate.prefix_key("short", 50) == ""
    assert boilerplate.prefix_key(None, 5) == ""


def test_groups_need_same_site_and_min_count():
    arts = [art(i, "a.com", FURNITURE + " tail") for i in range(1, 6)]
    arts += [art(10, "b.com", FURNITURE)]                         # same text, other site: no group
    arts += [art(20 + i, "a.com", f"Real article number {i} about something " * 5) for i in range(5)]
    groups = boilerplate.find_boilerplate(arts, prefix_chars=60, min_count=5)
    assert len(groups) == 1
    (domain, _), ids = next(iter(groups.items()))
    assert domain == "a.com" and ids == [1, 2, 3, 4, 5]


def test_different_endings_still_group_by_opening():
    arts = [art(i, "a.com", FURNITURE + f" different ending {i}") for i in range(6)]
    assert len(boilerplate.find_boilerplate(arts, prefix_chars=60, min_count=5)) == 1


def test_summarize_counts_and_label_overlap():
    arts = [art(i, "a.com", FURNITURE) for i in range(1, 7)] + [art(99, "b.com", "x" * 200)]
    groups = boilerplate.find_boilerplate(arts, 60, 5)
    rep, affected = boilerplate.summarize(groups, len(arts), label_ids=[1, 2, 99])
    assert rep["articles_affected"] == 6 and affected == [1, 2, 3, 4, 5, 6]
    assert rep["share_affected"] == round(6 / 7, 4)
    assert rep["affected_in_hand_labels"] == 2 and rep["hand_labels_checked"] == 3
    assert rep["top_repeated_openings"][0]["articles"] == 6
    assert boilerplate.summarize({}, 0)[0]["share_affected"] == 0.0
