"""Core logic: find the user's comments and posts, overwrite them, delete them.

Works on PRAW objects but only touches a small duck-typed surface
(``id``, ``created_utc``, ``subreddit``, ``edit``, ``delete`` and, for posts,
``is_self``), so tests can pass in fakes.
"""

from __future__ import annotations

import json
import logging
import random
import string
import time
from dataclasses import dataclass, field
from typing import Callable, Iterable, Iterator, Optional

log = logging.getLogger("rippit")

# Reddit caps every listing at ~1000 items, so we walk several sort orders
# to reach items that one sort alone would hide.
LISTING_SORTS = ("new", "top", "controversial", "hot")

WORDS = (
    "amber anchor apple arrow aspen basil beacon birch bramble breeze cedar "
    "cinder clover cobalt copper coral dune ember fable fern flint garnet "
    "glade granite harbor hazel heron indigo ivory juniper kelp lantern "
    "lichen maple marble meadow mist moss nectar oak onyx orchid pebble "
    "pine prism quartz raven reed ridge river saffron sage shale slate "
    "sparrow spruce stone thistle thorn tide timber umber velvet willow "
    "wren yarrow zephyr"
).split()


def random_text(rng: random.Random, min_words: int = 12, max_words: int = 40) -> str:
    """Plausible-looking filler so the overwrite doesn't stand out as a wipe."""
    words = [rng.choice(WORDS) for _ in range(rng.randint(min_words, max_words))]
    words[0] = words[0].capitalize()
    tag = "".join(rng.choices(string.ascii_lowercase + string.digits, k=6))
    return " ".join(words) + f". {tag}"


@dataclass
class Filters:
    older_than_days: Optional[float] = None
    subreddits: set[str] = field(default_factory=set)
    exclude_subreddits: set[str] = field(default_factory=set)
    keep_ids: set[str] = field(default_factory=set)

    def matches(self, item, now: float) -> bool:
        if item.id in self.keep_ids:
            return False
        sub = str(item.subreddit).lower()
        if self.subreddits and sub not in self.subreddits:
            return False
        if sub in self.exclude_subreddits:
            return False
        if self.older_than_days is not None:
            if now - item.created_utc < self.older_than_days * 86400:
                return False
        return True


@dataclass
class Options:
    comments: bool = True
    posts: bool = True
    execute: bool = False  # False = dry run, nothing is changed
    delete: bool = True  # False = overwrite only, leave the item up
    overwrite_passes: int = 1
    delay: float = 1.0  # seconds between items, on top of PRAW's rate limiting
    max_rounds: int = 10  # re-scan listings until a round finds nothing new


@dataclass
class Stats:
    seen: int = 0
    skipped: int = 0
    overwritten: int = 0
    deleted: int = 0
    errors: int = 0


def iter_listing(listing_owner, seen: set[str]) -> Iterator:
    """Yield each unseen item from every sort order of a redditor listing."""
    for sort in LISTING_SORTS:
        method = getattr(listing_owner, sort)
        kwargs = {"limit": None}
        if sort in ("top", "controversial"):
            kwargs["time_filter"] = "all"
        for item in method(**kwargs):
            if item.id in seen:
                continue
            seen.add(item.id)
            yield item


def is_editable(item, kind: str) -> bool:
    # Link, image and video posts have no body text to edit.
    return kind == "comment" or bool(getattr(item, "is_self", False))


def original_text(item, kind: str) -> str:
    if kind == "comment":
        return getattr(item, "body", "")
    return getattr(item, "selftext", "") or getattr(item, "url", "")


def process_item(
    item,
    kind: str,
    opts: Options,
    stats: Stats,
    rng: random.Random,
    backup: Optional[Callable[[dict], None]],
) -> None:
    label = f"{kind} {item.id} in r/{item.subreddit}"
    if not opts.execute:
        action = "overwrite + delete" if opts.delete else "overwrite"
        if not is_editable(item, kind):
            action = "delete (link post, can't overwrite)" if opts.delete else "skip (link post)"
        log.info("[dry run] would %s: %s", action, label)
        return

    if backup is not None:
        backup(
            {
                "kind": kind,
                "id": item.id,
                "subreddit": str(item.subreddit),
                "created_utc": item.created_utc,
                "title": getattr(item, "title", None),
                "text": original_text(item, kind),
                "permalink": getattr(item, "permalink", None),
            }
        )

    if is_editable(item, kind):
        try:
            for _ in range(opts.overwrite_passes):
                item.edit(random_text(rng))
            stats.overwritten += 1
            log.info("overwrote %s", label)
        except Exception as exc:  # archived/locked items reject edits
            stats.errors += 1
            log.warning("could not overwrite %s: %s", label, exc)

    if opts.delete:
        try:
            item.delete()
            stats.deleted += 1
            log.info("deleted %s", label)
        except Exception as exc:
            stats.errors += 1
            log.warning("could not delete %s: %s", label, exc)

    if opts.delay:
        time.sleep(opts.delay)


def wipe(
    redditor,
    opts: Options,
    filters: Filters,
    backup: Optional[Callable[[dict], None]] = None,
    now: Optional[float] = None,
    rng: Optional[random.Random] = None,
) -> Stats:
    now = time.time() if now is None else now
    rng = rng or random.SystemRandom()
    stats = Stats()
    kinds = []
    if opts.comments:
        kinds.append(("comment", redditor.comments))
    if opts.posts:
        kinds.append(("post", redditor.submissions))

    for kind, owner in kinds:
        seen: set[str] = set()
        # A deleted item drops out of the listings, which can surface older
        # items past the 1000 cap, so keep scanning while we make progress.
        # A dry run changes nothing, so one round is all it can see.
        rounds = opts.max_rounds if opts.execute else 1
        for _ in range(rounds):
            found = 0
            for item in iter_listing(owner, seen):
                found += 1
                stats.seen += 1
                if not filters.matches(item, now):
                    stats.skipped += 1
                    continue
                process_item(item, kind, opts, stats, rng, backup)
            if found == 0 or not opts.delete:
                break
    return stats


def jsonl_writer(path: str) -> Callable[[dict], None]:
    def write(record: dict) -> None:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    return write


def lower_set(values: Iterable[str]) -> set[str]:
    return {v.lower().removeprefix("r/") for v in values}
