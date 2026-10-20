import random

from rippit.wipe import Filters, Options, wipe

NOW = 1_800_000_000
DAY = 86400


class FakeItem:
    def __init__(self, store, id, sub="python", age_days=10, is_self=True, fail_edit=False):
        self.store = store
        self.id = id
        self.subreddit = sub
        self.created_utc = NOW - age_days * DAY
        self.is_self = is_self
        self.body = self.selftext = "original"
        self.fail_edit = fail_edit
        self.edits = []
        self.deleted = False

    def edit(self, text):
        if self.fail_edit:
            raise RuntimeError("archived")
        self.edits.append(text)

    def delete(self):
        self.deleted = True
        self.store.remove(self)


class FakeListing:
    """Mimics a redditor listing that only shows the first `cap` live items."""

    def __init__(self, items, cap=1000):
        self.items = items
        self.cap = cap

    def _list(self, limit=None, time_filter=None):
        return list(self.items[: self.cap])

    new = top = controversial = hot = _list

    def remove(self, item):
        self.items.remove(item)


class FakeRedditor:
    def __init__(self, comments=(), posts=(), cap=1000):
        self.comments = FakeListing([], cap)
        self.submissions = FakeListing([], cap)
        for spec in comments:
            self.comments.items.append(FakeItem(self.comments, **spec))
        for spec in posts:
            self.submissions.items.append(FakeItem(self.submissions, **spec))


def run(redditor, **kw):
    filters = kw.pop("filters", Filters())
    opts = Options(delay=0, **kw)
    return wipe(redditor, opts, filters, now=NOW, rng=random.Random(0))


def test_dry_run_changes_nothing():
    r = FakeRedditor(comments=[{"id": "c1"}], posts=[{"id": "p1"}])
    stats = run(r)
    assert stats.seen == 2 and stats.deleted == 0 and stats.overwritten == 0
    assert len(r.comments.items) == 1 and r.comments.items[0].edits == []


def test_execute_overwrites_then_deletes_comments_and_posts():
    r = FakeRedditor(comments=[{"id": "c1"}, {"id": "c2"}], posts=[{"id": "p1"}])
    kept = list(r.comments.items) + list(r.submissions.items)
    stats = run(r, execute=True)
    assert stats.overwritten == 3 and stats.deleted == 3 and stats.errors == 0
    assert all(i.deleted and len(i.edits) == 1 and i.edits[0] != "original" for i in kept)


def test_link_posts_are_deleted_without_edit():
    r = FakeRedditor(posts=[{"id": "p1", "is_self": False}])
    item = r.submissions.items[0]
    stats = run(r, execute=True, comments=False)
    assert item.edits == [] and item.deleted and stats.overwritten == 0


def test_no_delete_only_overwrites():
    r = FakeRedditor(comments=[{"id": "c1"}])
    stats = run(r, execute=True, delete=False, overwrite_passes=3)
    assert stats.deleted == 0 and len(r.comments.items[0].edits) == 3


def test_edit_failure_still_deletes():
    r = FakeRedditor(comments=[{"id": "c1", "fail_edit": True}])
    stats = run(r, execute=True)
    assert stats.errors == 1 and stats.deleted == 1


def test_filters():
    r = FakeRedditor(
        comments=[
            {"id": "new", "age_days": 1},
            {"id": "old", "age_days": 100},
            {"id": "other", "age_days": 100, "sub": "AskReddit"},
            {"id": "keepme", "age_days": 100},
        ]
    )
    f = Filters(older_than_days=30, exclude_subreddits={"askreddit"}, keep_ids={"keepme"})
    stats = run(r, execute=True, posts=False, filters=f)
    assert stats.deleted == 1
    assert sorted(i.id for i in r.comments.items) == ["keepme", "new", "other"]


def test_rescans_past_listing_cap():
    r = FakeRedditor(comments=[{"id": f"c{n}"} for n in range(25)], cap=10)
    stats = run(r, execute=True, posts=False)
    assert stats.deleted == 25 and r.comments.items == []
