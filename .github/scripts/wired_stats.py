#!/usr/bin/env python3
"""Generate github-metrics.svg for the README ("SIGNAL STRENGTH").

Pulls real numbers from the GitHub GraphQL API using a personal access token
(so private repos / private contributions are counted too) and draws a single
self-contained SVG in the README's violet palette.

    METRICS_TOKEN=ghp_xxx python .github/scripts/wired_stats.py
    python .github/scripts/wired_stats.py --demo      # offline preview, fake data
"""
import datetime as dt
import json
import os
import random
import sys
import urllib.request
from html import escape

LOGIN = os.environ.get("WIRED_USER", "khadimshiny2-beep")
OUT = os.environ.get("WIRED_OUT", "github-metrics.svg")
TOKEN = os.environ.get("METRICS_TOKEN") or os.environ.get("GITHUB_TOKEN")

# Notebook "bytes" are mostly cell output, not code, so they skew the chart.
# Remove an entry (or empty the set) to count it.
EXCLUDE_LANGS = {"Jupyter Notebook"}
MAX_LANGS = 6

# palette (matches banner.svg)
BG, PANEL, BORDER = "#12101c", "#181526", "#2a2440"
TRACK, TEXT, MUTED = "#1d1a2e", "#e8e6f7", "#7c6fae"
LAV, LAV2 = "#b9a6ff", "#a08cff"
BAR_COLORS = ["#b9a6ff", "#a08cff", "#8f7bf0", "#7c6fd0", "#6b5fb0", "#5b5190"]
HEAT = [TRACK, "#3b2f6b", "#6a56b8", "#a08cff", "#e8e6f7"]
FONT = "'Fira Code','JetBrains Mono','DejaVu Sans Mono',Menlo,Consolas,monospace"

API = "https://api.github.com/graphql"

MAIN_Q = """
query($login:String!){
  user(login:$login){
    createdAt
    followers{ totalCount }
    pullRequests{ totalCount }
    issues{ totalCount }
    repositories(ownerAffiliations:OWNER, isFork:false, first:100,
                 orderBy:{field:PUSHED_AT, direction:DESC}){
      totalCount
      nodes{
        stargazerCount
        languages(first:12, orderBy:{field:SIZE, direction:DESC}){
          edges{ size node{ name } }
        }
      }
    }
    contributionsCollection{
      totalCommitContributions
      totalPullRequestReviewContributions
      contributionCalendar{
        totalContributions
        weeks{ contributionDays{ date contributionCount } }
      }
    }
  }
}"""

YEAR_Q = """
query($login:String!, $from:DateTime!, $to:DateTime!){
  user(login:$login){
    contributionsCollection(from:$from, to:$to){
      contributionCalendar{
        weeks{ contributionDays{ date contributionCount } }
      }
    }
  }
}"""


def gql(query, variables):
    req = urllib.request.Request(
        API,
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={
            "Authorization": f"bearer {TOKEN}",
            "User-Agent": "wired-stats",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        body = json.load(r)
    if body.get("errors"):
        raise RuntimeError(body["errors"])
    return body["data"]["user"]


def days_of(calendar):
    return {
        d["date"]: d["contributionCount"]
        for w in calendar["weeks"]
        for d in w["contributionDays"]
    }


def streaks(counts, today):
    """counts: {iso-date: n}. Returns (current, longest) as (length, start, end)."""
    active = {dt.date.fromisoformat(d) for d, n in counts.items() if n > 0}
    # current: today may still be empty, so allow starting from yesterday
    d = today if today in active else today - dt.timedelta(days=1)
    cur_end, length = d, 0
    while d in active:
        length += 1
        d -= dt.timedelta(days=1)
    cur = (length, d + dt.timedelta(days=1), cur_end) if length else (0, None, None)
    best, run, start, prev = (0, None, None), 0, None, None
    for day in sorted(active):
        if prev and day - prev == dt.timedelta(days=1):
            run += 1
        else:
            run, start = 1, day
        if run > best[0]:
            best = (run, start, day)
        prev = day
    return cur, best


def collect():
    now = dt.datetime.now(dt.timezone.utc)
    me = gql(MAIN_Q, {"login": LOGIN})
    cc = me["contributionsCollection"]
    cal = cc["contributionCalendar"]

    # full history (one call per calendar year) for an honest "longest streak"
    counts = {}
    first = int(me["createdAt"][:4])
    for year in range(first, now.year + 1):
        y = gql(YEAR_Q, {
            "login": LOGIN,
            "from": f"{year}-01-01T00:00:00Z",
            "to": f"{year}-12-31T23:59:59Z",
        })
        counts.update(days_of(y["contributionsCollection"]["contributionCalendar"]))
    counts.update(days_of(cal))
    cur, best = streaks(counts, now.date())

    stars, langs = 0, {}
    for repo in me["repositories"]["nodes"]:
        stars += repo["stargazerCount"]
        for e in repo["languages"]["edges"]:
            n = e["node"]["name"]
            if n not in EXCLUDE_LANGS:
                langs[n] = langs.get(n, 0) + e["size"]
    total = sum(langs.values()) or 1
    top = sorted(langs.items(), key=lambda kv: -kv[1])[:MAX_LANGS]

    return {
        "contributions": cal["totalContributions"],
        "commits": cc["totalCommitContributions"],
        "reviews": cc["totalPullRequestReviewContributions"],
        "stars": stars,
        "prs": me["pullRequests"]["totalCount"],
        "issues": me["issues"]["totalCount"],
        "repos": me["repositories"]["totalCount"],
        "cur": cur,
        "best": best,
        "langs": [(n, b * 100 / total) for n, b in top],
        "weeks": [[d["contributionCount"] for d in w["contributionDays"]]
                  for w in cal["weeks"]],
        "updated": now.strftime("%Y-%m-%d %H:%M UTC"),
    }


def demo():
    random.seed(7)
    today = dt.date.today()
    weeks = [[random.choice([0, 0, 0, 1, 2, 4, 7]) for _ in range(7)] for _ in range(53)]
    return {
        "contributions": 94, "commits": 70, "reviews": 0, "stars": 15, "prs": 1,
        "issues": 0, "repos": 22,
        "cur": (1, today, today),
        "best": (3, today - dt.timedelta(days=95), today - dt.timedelta(days=93)),
        "langs": [("Python", 48.2), ("Nix", 14.9), ("HTML", 12.7), ("C", 9.8),
                  ("Rust", 7.4), ("JavaScript", 5.1)],
        "weeks": weeks,
        "updated": "demo",
    }


# ------------------------------------------------------------------ drawing
def fmt(d):
    return d.strftime("%-d %b") if d else "-"


def text(x, y, s, size=12, fill=TEXT, anchor="start", weight="normal", extra=""):
    return (f'<text x="{x}" y="{y}" font-family="{FONT}" font-size="{size}" '
            f'fill="{fill}" text-anchor="{anchor}" font-weight="{weight}" {extra}>'
            f'{escape(str(s))}</text>')


def render(s):
    W = 860
    o = []
    add = o.append

    # tiles
    tiles = [
        ("CONTRIBUTIONS", s["contributions"], "last 12 months", TEXT),
        ("CURRENT STREAK", f'{s["cur"][0]}d',
         f'since {fmt(s["cur"][1])}' if s["cur"][0] else "no active streak", LAV),
        ("LONGEST STREAK", f'{s["best"][0]}d',
         f'{fmt(s["best"][1])} - {fmt(s["best"][2])}' if s["best"][0] else "-", TEXT),
        ("COMMITS", s["commits"], "last 12 months", TEXT),
    ]
    tw, gap, ty = 190, 12, 70
    for i, (label, val, sub, color) in enumerate(tiles):
        x = 32 + i * (tw + gap)
        add(f'<rect x="{x}" y="{ty}" width="{tw}" height="86" rx="8" fill="{PANEL}" stroke="{BORDER}"/>')
        add(text(x + 16, ty + 24, label, 10, MUTED))
        add(text(x + 16, ty + 56, val, 30, color, weight="bold"))
        add(text(x + 16, ty + 75, sub, 10, MUTED))

    # small stats row
    items = [("STARS", s["stars"]), ("PRS", s["prs"]), ("ISSUES", s["issues"]),
             ("REVIEWS", s["reviews"]), ("REPOS", s["repos"])]
    ry = ty + 86 + 34
    for i, (k, v) in enumerate(items):
        x = 32 + i * 160
        add(f'<text x="{x}" y="{ry}" font-family="{FONT}" font-size="12">'
            f'<tspan fill="{MUTED}">{k} </tspan><tspan fill="{TEXT}" font-weight="bold">{v}</tspan></text>')

    # languages
    ly = ry + 40
    add(f'<line x1="32" y1="{ly-18}" x2="{W-32}" y2="{ly-18}" stroke="{BORDER}"/>')
    add(text(32, ly, "LANGUAGES IN THE WIRED", 12, LAV, weight="bold"))
    bx, bw = 190, 520
    for i, (name, pct) in enumerate(s["langs"]):
        y = ly + 28 + i * 28
        fill = BAR_COLORS[min(i, len(BAR_COLORS) - 1)]
        w = max(4, round(bw * pct / 100, 1))
        add(text(32, y, name, 12))
        add(f'<rect x="{bx}" y="{y-10}" width="{bw}" height="10" rx="5" fill="{TRACK}"/>')
        add(f'<rect x="{bx}" y="{y-10}" width="{w}" height="10" rx="5" fill="{fill}">'
            f'<animate attributeName="width" from="0" to="{w}" dur="1.1s" begin="{i*0.12:.2f}s" fill="freeze"/></rect>')
        add(text(W - 32, y, f"{pct:.1f}%", 12, MUTED, "end"))
    ly_end = ly + 28 + max(len(s["langs"]) - 1, 0) * 28

    # heatmap
    hy = ly_end + 46
    add(f'<line x1="32" y1="{hy-30}" x2="{W-32}" y2="{hy-30}" stroke="{BORDER}"/>')
    add(text(32, hy-8, "PULSE OF THE WIRED", 12, LAV, weight="bold"))
    peak = max((c for w in s["weeks"] for c in w), default=0) or 1
    for wi, week in enumerate(s["weeks"]):
        for di, c in enumerate(week):
            lvl = 0 if c == 0 else min(4, 1 + int(3 * (c - 1) / max(peak - 1, 1) + 0.5)) if peak > 1 else 1
            add(f'<rect x="{32 + wi*15}" y="{hy + di*15}" width="12" height="12" rx="3" fill="{HEAT[lvl]}"/>')

    H = hy + 7 * 15 + 30
    add(text(W - 32, H - 12, f"synced {s['updated']}", 9, MUTED, "end"))

    head = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="GitHub stats">',
        f'<rect x="0.5" y="0.5" width="{W-1}" height="{H-1}" rx="10" fill="{BG}" stroke="{BORDER}"/>',
        text(32, 40, "WIRED STATUS", 14, LAV, weight="bold"),
        text(172, 40, "// layer 07", 12, MUTED),
        f'<rect x="268" y="29" width="8" height="14" fill="{LAV2}"><animate attributeName="opacity" values="1;0;1" dur="1.2s" repeatCount="indefinite"/></rect>',
    ]
    return "\n".join(head + o + ["</svg>"])


def main():
    if "--demo" in sys.argv:
        stats = demo()
    else:
        if not TOKEN:
            sys.exit("Set METRICS_TOKEN (a personal access token) first.")
        stats = collect()
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(render(stats))
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
