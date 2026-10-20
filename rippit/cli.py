"""Command-line entry point: ``rippit`` (or ``python -m rippit``)."""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time

from . import __version__
from .wipe import Filters, Options, jsonl_writer, lower_set, wipe

ENV_VARS = ("REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", "REDDIT_USERNAME", "REDDIT_PASSWORD")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="rippit",
        description="Overwrite and then delete your own Reddit comments and posts. "
        "Runs as a dry run unless you pass --execute.",
    )
    p.add_argument("--execute", action="store_true", help="actually edit and delete (default is a dry run)")
    what = p.add_mutually_exclusive_group()
    what.add_argument("--comments-only", action="store_true", help="only touch comments")
    what.add_argument("--posts-only", action="store_true", help="only touch posts")
    p.add_argument("--no-delete", action="store_true", help="overwrite but leave items up")
    p.add_argument("--passes", type=int, default=1, help="times to overwrite each item before deleting (default 1)")
    p.add_argument("--older-than", type=float, metavar="DAYS", help="only items older than DAYS days")
    p.add_argument("--subreddit", action="append", default=[], metavar="NAME", help="only these subreddits (repeatable)")
    p.add_argument("--exclude-subreddit", action="append", default=[], metavar="NAME", help="skip these subreddits (repeatable)")
    p.add_argument("--keep", action="append", default=[], metavar="ID", help="skip the item with this id (repeatable)")
    p.add_argument("--delay", type=float, default=1.0, help="seconds to wait between items (default 1)")
    p.add_argument(
        "--backup",
        metavar="FILE",
        default=f"rippit-log-{time.strftime('%Y%m%d-%H%M%S')}.jsonl",
        help="where to save the original text before overwriting (default rippit-log-<time>.jsonl)",
    )
    p.add_argument("--no-backup", action="store_true", help="don't save a local copy of the originals")
    p.add_argument("--yes", action="store_true", help="skip the confirmation prompt with --execute")
    p.add_argument("-q", "--quiet", action="store_true", help="only print warnings and the summary")
    p.add_argument("--version", action="version", version=f"rippit {__version__}")
    return p


def make_reddit():
    import praw  # imported here so --help works without praw installed

    missing = [v for v in ENV_VARS if not os.environ.get(v)]
    if missing:
        sys.exit(f"Missing environment variables: {', '.join(missing)} (see .env.example)")
    return praw.Reddit(
        client_id=os.environ["REDDIT_CLIENT_ID"],
        client_secret=os.environ["REDDIT_CLIENT_SECRET"],
        username=os.environ["REDDIT_USERNAME"],
        password=os.environ["REDDIT_PASSWORD"],
        user_agent=f"rippit/{__version__} (by u/{os.environ['REDDIT_USERNAME']})",
        ratelimit_seconds=300,
    )


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.WARNING if args.quiet else logging.INFO, format="%(message)s")

    opts = Options(
        comments=not args.posts_only,
        posts=not args.comments_only,
        execute=args.execute,
        delete=not args.no_delete,
        overwrite_passes=max(1, args.passes),
        delay=args.delay if args.execute else 0,
    )
    filters = Filters(
        older_than_days=args.older_than,
        subreddits=lower_set(args.subreddit),
        exclude_subreddits=lower_set(args.exclude_subreddit),
        keep_ids=set(args.keep),
    )

    reddit = make_reddit()
    me = reddit.user.me()
    if me is None:
        sys.exit("Could not log in. Check your credentials (and 2FA code, if you use one).")

    if args.execute and not args.yes:
        targets = " and ".join(k for k, on in (("comments", opts.comments), ("posts", opts.posts)) if on)
        verb = "overwrite" if args.no_delete else "overwrite and DELETE"
        answer = input(f"This will {verb} the matching {targets} of u/{me.name}. This cannot be undone. Type the username to continue: ")
        if answer.strip().lower().removeprefix("u/") != me.name.lower():
            print("Aborted.")
            return 1

    backup = None if (args.no_backup or not args.execute) else jsonl_writer(args.backup)
    stats = wipe(me, opts, filters, backup=backup)

    mode = "" if args.execute else " (dry run, nothing changed)"
    print(
        f"\nDone{mode}: {stats.seen} found, {stats.skipped} skipped by filters, "
        f"{stats.overwritten} overwritten, {stats.deleted} deleted, {stats.errors} errors."
    )
    if backup is not None:
        print(f"Originals saved to {args.backup}")
    return 1 if stats.errors else 0


if __name__ == "__main__":
    sys.exit(main())
