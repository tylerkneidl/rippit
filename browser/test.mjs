// Runs browser/rippit.js against a fake old.reddit.com: node browser/test.mjs
import { readFileSync } from "node:fs";
import assert from "node:assert/strict";
import vm from "node:vm";

const src = readFileSync(new URL("./rippit.js", import.meta.url), "utf8");
const now = Date.now() / 1000;

function fakeReddit({ comments, posts, cap = 1000 }) {
  const items = { comments, submitted: posts };
  const calls = { edits: [], dels: [] };
  async function fetch(url, opts = {}) {
    const u = new URL(url, "https://old.reddit.com");
    const json = (data) => ({ ok: true, status: 200, headers: new Map(), json: async () => data });
    if (u.pathname === "/api/me.json") return json({ data: { name: "tester", modhash: "mh" } });
    const m = u.pathname.match(/^\/user\/tester\/(comments|submitted)\.json$/);
    if (m) {
      const live = items[m[1]].slice(0, cap);
      const start = u.searchParams.get("after") ? live.findIndex((i) => i.name === u.searchParams.get("after")) + 1 : 0;
      const page = live.slice(start, start + 100);
      const after = start + 100 < live.length ? page.at(-1).name : null;
      return json({ data: { children: page.map((d) => ({ data: d })), after } });
    }
    const body = Object.fromEntries(opts.body);
    assert.equal(body.uh, "mh");
    if (u.pathname === "/api/editusertext") { calls.edits.push(body.thing_id); return json({ json: { errors: [] } }); }
    if (u.pathname === "/api/del") {
      calls.dels.push(body.id);
      for (const k in items) items[k] = items[k].filter((i) => i.name !== body.id);
      return json({});
    }
    throw new Error("unexpected " + url);
  }
  return { fetch, calls, items };
}

const mk = (prefix, n, extra = {}) => Array.from({ length: n }, (_, i) => ({
  name: `${prefix}_${i}`, id: String(i), subreddit: "python", created_utc: now - 100 * 86400,
  body: "orig", title: "t", is_self: true, selftext: "s", permalink: "/r/x", ...extra }));

async function run(settings, reddit) {
  let code = src;
  for (const [k, v] of Object.entries({ DELAY_MS: 0, ...settings })) {
    code = code.replace(new RegExp(`const ${k} = [^;]+;`), `const ${k} = ${JSON.stringify(v)};`);
  }
  const logs = [], downloads = [];
  const ctx = {
    fetch: reddit.fetch, URLSearchParams, URL, Blob, setTimeout, console: { log: (s) => logs.push(s), warn: (s) => logs.push(s), error: (s) => logs.push(s) },
    location: { hostname: "old.reddit.com" }, prompt: () => "tester",
    document: { createElement: () => ({ click() {}, remove() {} }), body: { appendChild: (a) => downloads.push(a.download) } },
  };
  ctx.URL = { createObjectURL: () => "blob:" };
  await vm.runInNewContext(code, ctx);
  return { logs, downloads };
}

// Dry run touches nothing.
let r = fakeReddit({ comments: mk("t1", 3), posts: mk("t3", 2) });
let out = await run({}, r);
assert.deepEqual(r.calls, { edits: [], dels: [] });
assert.match(out.logs.at(-1), /5 found.*0 deleted/);

// Live run past a 100-item cap: everything edited then deleted, link post not edited.
r = fakeReddit({ comments: mk("t1", 250), posts: [...mk("t3", 2), ...mk("t3L", 1, { is_self: false })], cap: 100 });
out = await run({ DRY_RUN: false }, r);
assert.equal(r.calls.dels.length, 253);
assert.equal(r.calls.edits.length, 252);
assert.ok(!r.calls.edits.includes("t3L_0"));
assert.ok(out.downloads.length >= 2);

// Filters.
r = fakeReddit({ comments: [...mk("old", 2), ...mk("new", 2, { created_utc: now }), ...mk("ask", 1, { subreddit: "AskReddit" })], posts: [] });
await run({ DRY_RUN: false, OLDER_THAN_DAYS: 30, SKIP_SUBREDDITS: ["askreddit"], KEEP_IDS: ["old_1"] }, r);
assert.deepEqual(r.calls.dels, ["old_0"]);

console.log("browser tests passed");
