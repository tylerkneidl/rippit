# rippit

Overwrite and then delete all of your own Reddit comments and posts.

Deleting alone isn't enough: third-party archives and caches often keep the
last text they saw. rippit first edits each comment (and each text post) to
random filler, then deletes it. Link, image and video posts have no body to
edit, so they're just deleted.

**This is irreversible.** rippit runs as a dry run unless you pass `--execute`,
and before it overwrites anything it saves the originals to a local
`rippit-log-<time>.jsonl` file.

## Setup

1. Go to <https://www.reddit.com/prefs/apps>, click **create another app**,
   choose **script**, and use `http://localhost:8080` as the redirect URI.
   The client id is the short string under the app name; the secret is labeled.
2. Install:

   ```sh
   pip install .
   ```

3. Copy `.env.example` to `.env`, fill it in, and load it:

   ```sh
   set -a; source .env; set +a
   ```

   If your account uses 2FA, set `REDDIT_PASSWORD` to `password:123456` with
   the current code, right before running.

## Usage

```sh
rippit                       # dry run: lists what would be overwritten and deleted
rippit --execute             # do it (asks you to type your username to confirm)
```

Useful options:

| Option | Effect |
| --- | --- |
| `--comments-only` / `--posts-only` | limit to one kind |
| `--older-than 30` | only items older than 30 days |
| `--subreddit NAME` | only these subreddits (repeatable) |
| `--exclude-subreddit NAME` | skip these subreddits (repeatable) |
| `--keep ID` | skip one item by id (repeatable) |
| `--no-delete` | overwrite but leave the item up |
| `--passes N` | overwrite N times before deleting |
| `--no-backup` | don't save the originals locally |
| `--delay S` | pause between items (default 1s) |

Run `rippit --help` for the full list.

## Notes

- Reddit listings stop at about 1000 items per sort order. rippit walks the
  new, top, controversial and hot listings, and after deleting it re-scans
  until nothing new shows up, which reaches older items as newer ones go away.
  If you have far more than that, a run may still leave some; running again
  or requesting your data export from Reddit and deleting by id are options.
- Items in archived or locked threads can't be edited; rippit logs the error
  and still deletes them.
- PRAW handles Reddit's rate limits; a large history can take a while.

## Development

```sh
pip install -e '.[dev]'
pytest
```
