# rippit

Overwrite and then delete all of your own Reddit comments and posts.

Deleting alone isn't enough: third-party archives and caches often keep the
last text they saw. rippit first edits each comment (and each text post) to
random filler, then deletes it. Link, image and video posts have no body to
edit, so they're just deleted.

**This is irreversible.** The CLI is a dry run unless you pass `--execute`; the
browser script asks you to type your username first. Both save a local backup of the original text before they overwrite anything.

## Two ways to run it

**Browser script (no API key).** Reddit stopped handing out API keys on request
in November 2025 ([Responsible Builder Policy](https://support.reddithelp.com/hc/en-us/articles/42728983564564-Responsible-Builder-Policy)),
so the simplest option is [`browser/rippit.js`](browser/rippit.js). It uses
your logged-in session, the same way the site's own edit and delete buttons do.

1. Log in at <https://old.reddit.com> (it must be **old**.reddit.com).
2. Open the browser console (F12, or Cmd+Option+J on a Mac).
3. Paste the whole of `browser/rippit.js` and press Enter, then type your
   username when asked. It overwrites and deletes everything that matches the
   settings at the top. Set `DRY_RUN = true` there to only list what would change.

It downloads a JSON backup of the originals before it changes anything. Keep
the tab open and in front until it prints `rippit: done`.

**Python CLI (needs API credentials).** Use this if you already have a Reddit
"script" app from before November 2025, or once Reddit approves an access
request you send through
[Developer Support](https://support.reddithelp.com/hc/en-us/requests/new?ticket_form_id=14868593862164).

## CLI setup

1. Get a script app's client id and secret (see above). For the redirect URI
   use `http://localhost:8080`.
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

## CLI usage

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
node browser/test.mjs   # browser script against a fake Reddit
```
