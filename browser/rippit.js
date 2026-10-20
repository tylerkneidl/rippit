// rippit (browser edition): overwrite and delete your own Reddit comments and posts.
//
// No API key needed. It uses your logged-in session the same way the site's own
// edit and delete buttons do.
//
// 1. Log in at https://old.reddit.com and stay on any old.reddit.com page.
// 2. Open the browser console (F12, or Cmd+Option+J on a Mac).
// 3. Paste this whole file and press Enter. It asks you to type your username,
//    then overwrites and deletes. Set DRY_RUN to true below to preview instead.
//
// Before changing anything it downloads a JSON backup of the original text.

(async () => {
  // ---- settings --------------------------------------------------------
  const DRY_RUN = false;         // true = only list what would change
  const DO_COMMENTS = true;
  const DO_POSTS = true;
  const DELETE = true;           // false = overwrite only, leave items up
  const OVERWRITE_PASSES = 1;
  const OLDER_THAN_DAYS = null;  // e.g. 30 to keep the last month
  const ONLY_SUBREDDITS = [];    // e.g. ["pics", "AskReddit"]; empty = all
  const SKIP_SUBREDDITS = [];
  const KEEP_IDS = [];           // e.g. ["t1_abc123", "t3_def456"]
  const DELAY_MS = 1500;         // pause between requests
  const MAX_ROUNDS = 10;         // re-scan after deleting to get past the 1000-item cap
  // ----------------------------------------------------------------------

  // Reddit listings stop at ~1000 items per sort, so walk several sorts.
  const SORTS = ["new", "top", "controversial", "hot"];
  const WORDS = ("amber anchor apple arrow aspen basil beacon birch bramble breeze cedar cinder " +
    "clover cobalt copper coral dune ember fable fern flint garnet glade granite harbor hazel " +
    "heron indigo ivory juniper kelp lantern lichen maple marble meadow mist moss nectar oak " +
    "onyx orchid pebble pine prism quartz raven reed ridge river saffron sage shale slate " +
    "sparrow spruce stone thistle thorn tide timber umber velvet willow wren yarrow zephyr").split(" ");

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const pick = (a) => a[Math.floor(Math.random() * a.length)];
  const lower = (a) => new Set(a.map((s) => s.toLowerCase().replace(/^r\//, "")));
  const only = lower(ONLY_SUBREDDITS);
  const skip = lower(SKIP_SUBREDDITS);
  const keep = new Set(KEEP_IDS);
  const now = Date.now() / 1000;

  function randomText() {
    const n = 12 + Math.floor(Math.random() * 29);
    const words = Array.from({ length: n }, () => pick(WORDS));
    words[0] = words[0][0].toUpperCase() + words[0].slice(1);
    return words.join(" ") + ". " + Math.random().toString(36).slice(2, 8);
  }

  async function request(url, opts = {}, tries = 5) {
    for (let i = 0; i < tries; i++) {
      const res = await fetch(url, { credentials: "include", ...opts });
      if (res.status === 429 || res.status >= 500) {
        const wait = (Number(res.headers.get("retry-after")) || 2 ** (i + 2)) * 1000;
        console.warn(`rippit: ${res.status} from Reddit, waiting ${wait / 1000}s`);
        await sleep(wait);
        continue;
      }
      if (!res.ok) throw new Error(`${res.status} ${res.statusText} for ${url}`);
      return res.json();
    }
    throw new Error(`gave up after ${tries} tries: ${url}`);
  }

  async function post(path, params) {
    const body = new URLSearchParams({ ...params, uh: modhash, api_type: "json" });
    const out = await request(`/api/${path}`, { method: "POST", body });
    const errors = out?.json?.errors;
    if (errors && errors.length) throw new Error(errors.map((e) => e.join(": ")).join("; "));
    await sleep(DELAY_MS);
    return out;
  }

  async function* listing(user, kind, seen) {
    const where = kind === "comment" ? "comments" : "submitted";
    for (const sort of SORTS) {
      let after = "";
      do {
        const t = sort === "top" || sort === "controversial" ? "&t=all" : "";
        const page = await request(`/user/${user}/${where}.json?limit=100&raw_json=1&sort=${sort}${t}&after=${after}`);
        await sleep(DELAY_MS);
        for (const child of page.data.children) {
          if (seen.has(child.data.name)) continue;
          seen.add(child.data.name);
          yield child.data;
        }
        after = page.data.after || "";
        console.log(`rippit: reading your ${where} (${sort})... ${seen.size} found so far`);
      } while (after);
    }
  }

  function wanted(item) {
    const sub = item.subreddit.toLowerCase();
    if (keep.has(item.name) || keep.has(item.id)) return false;
    if (only.size && !only.has(sub)) return false;
    if (skip.has(sub)) return false;
    if (OLDER_THAN_DAYS != null && now - item.created_utc < OLDER_THAN_DAYS * 86400) return false;
    return true;
  }

  function download(name, data) {
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }));
    a.download = name;
    document.body.appendChild(a);
    a.click();
    a.remove();
  }

  // ---- run -------------------------------------------------------------
  if (location.hostname !== "old.reddit.com") {
    return console.error("rippit: open old.reddit.com first, then paste this again.");
  }
  const me = (await request("/api/me.json")).data;
  if (!me || !me.name) return console.error("rippit: you don't seem to be logged in.");
  const modhash = me.modhash;
  console.log(`rippit: logged in as u/${me.name}${DRY_RUN ? " (DRY RUN, nothing will change)" : ""}`);
  console.log("rippit: reading your history first; changes start once that's done.");

  if (!DRY_RUN) {
    const typed = prompt(`This will overwrite${DELETE ? " and DELETE" : ""} the matching comments/posts of u/${me.name}. ` +
      "It cannot be undone. Type your username to continue:");
    if ((typed || "").trim().toLowerCase().replace(/^u\//, "") !== me.name.toLowerCase()) {
      return console.log("rippit: aborted.");
    }
  }

  const stats = { found: 0, skipped: 0, overwritten: 0, deleted: 0, errors: 0 };
  const backup = [];
  const kinds = [DO_COMMENTS && "comment", DO_POSTS && "post"].filter(Boolean);

  // Collect matches first so the backup is saved before anything changes.
  // A deleted item drops out of the listings and can reveal older ones past
  // the 1000 cap, so live runs repeat until a round finds nothing new.
  for (const kind of kinds) {
    const seen = new Set();
    const rounds = DRY_RUN || !DELETE ? 1 : MAX_ROUNDS;
    for (let round = 1; round <= rounds; round++) {
      const batch = [];
      for await (const item of listing(me.name, kind, seen)) {
        stats.found++;
        if (wanted(item)) batch.push(item);
        else stats.skipped++;
      }
      if (!batch.length) break;
      console.log(`rippit: ${kind}s, round ${round}: ${batch.length} to process`);

      for (const item of batch) {
        const editable = kind === "comment" || item.is_self;
        const label = `${kind} ${item.name} in r/${item.subreddit}: ${(item.body || item.title || "").slice(0, 60)}`;
        if (DRY_RUN) {
          const action = editable ? (DELETE ? "overwrite + delete" : "overwrite") : (DELETE ? "delete (link post)" : "skip (link post)");
          console.log(`[dry run] would ${action}: ${label}`);
          continue;
        }
        backup.push({ kind, id: item.name, subreddit: item.subreddit, created_utc: item.created_utc,
          title: item.title ?? null, text: kind === "comment" ? item.body : (item.selftext || item.url),
          permalink: "https://www.reddit.com" + item.permalink });
      }

      if (!DRY_RUN) {
        download(`rippit-backup-${me.name}-${kind}s-round${round}-${Date.now()}.json`, backup.splice(0));
        for (const item of batch) {
          const editable = kind === "comment" || item.is_self;
          const label = `${kind} ${item.name} in r/${item.subreddit}`;
          if (editable) {
            try {
              for (let p = 0; p < OVERWRITE_PASSES; p++) await post("editusertext", { thing_id: item.name, text: randomText() });
              stats.overwritten++;
              console.log(`overwrote ${label}`);
            } catch (e) {
              stats.errors++; // archived or locked threads reject edits; still delete
              console.warn(`could not overwrite ${label}: ${e.message}`);
            }
          }
          if (DELETE) {
            try {
              await post("del", { id: item.name });
              stats.deleted++;
              console.log(`deleted ${label}`);
            } catch (e) {
              stats.errors++;
              console.warn(`could not delete ${label}: ${e.message}`);
            }
          }
        }
      }
    }
  }

  console.log(`rippit: done${DRY_RUN ? " (dry run, nothing changed)" : ""}. ` +
    `${stats.found} found, ${stats.skipped} skipped by filters, ${stats.overwritten} overwritten, ` +
    `${stats.deleted} deleted, ${stats.errors} errors.`);
})();
