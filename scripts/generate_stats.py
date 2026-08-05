#!/usr/bin/env python3
"""
generate_stats.py — draws stats.svg, streak.svg, langs.svg, year.svg
from the GitHub GraphQL API. Runs inside the nightly Action.

Deliberately uses ONLY the Python standard library — no dependency in
this file can break in CI. (The portrait pipeline is the one place
that needs extra packages, and it runs locally, not here.)

Env vars (set by the workflow):
    GITHUB_TOKEN   the built-in Actions token — no PAT needed
    GH_LOGIN       github.repository_owner
"""

import datetime as dt
import json
import os
import urllib.request

RAMP = " .`:-=+*cs#%@"
API_URL = "https://api.github.com/graphql"


def gh_graphql(query: str, variables: dict) -> dict:
    token = os.environ["GITHUB_TOKEN"]
    body = json.dumps({"query": query, "variables": variables}).encode("utf-8")
    req = urllib.request.Request(
        API_URL,
        data=body,
        headers={
            "Authorization": f"bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        payload = json.loads(resp.read())
    if "errors" in payload:
        raise RuntimeError(payload["errors"])
    return payload["data"]


# ---------------------------------------------------------------------------
# Trap #1: pin the window to whole UTC days. Left alone, contributionsCollection
# measures "the past year" from the moment of the request — two runs minutes
# apart bucket days into different weeks and shift the sparkline every night.
# ---------------------------------------------------------------------------
def get_utc_window():
    today = dt.datetime.now(dt.timezone.utc).date()
    to = dt.datetime.combine(today, dt.time(23, 59, 59), tzinfo=dt.timezone.utc)
    frm = dt.datetime.combine(
        today - dt.timedelta(days=364), dt.time(0, 0, 0), tzinfo=dt.timezone.utc
    )
    return frm.isoformat(), to.isoformat()


CONTRIB_QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      contributionCalendar {
        totalContributions
        weeks {
          contributionDays { date contributionCount }
        }
      }
    }
  }
}
"""

# Trap #2: filter repos to public only. A personal token sees private repos;
# the workflow's built-in token doesn't. Without this filter, language
# percentages disagree depending on who ran the script.
LANGS_QUERY = """
query($login: String!, $after: String) {
  user(login: $login) {
    repositories(first: 50, after: $after, privacy: PUBLIC,
                  ownerAffiliations: OWNER, isFork: false) {
      pageInfo { hasNextPage endCursor }
      nodes {
        name
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name color } }
        }
      }
    }
  }
}
"""


def fetch_contributions(login: str):
    frm, to = get_utc_window()
    data = gh_graphql(CONTRIB_QUERY, {"login": login, "from": frm, "to": to})
    cal = data["user"]["contributionsCollection"]["contributionCalendar"]
    days = []
    for week in cal["weeks"]:
        for d in week["contributionDays"]:
            days.append((d["date"], d["contributionCount"]))
    return cal["totalContributions"], days


def fetch_languages(login: str):
    by_bytes = {}
    by_repo_count = {}
    after = None
    while True:
        data = gh_graphql(LANGS_QUERY, {"login": login, "after": after})
        repos = data["user"]["repositories"]
        for repo in repos["nodes"]:
            for edge in repo["languages"]["edges"]:
                name = edge["node"]["name"]
                by_bytes[name] = by_bytes.get(name, 0) + edge["size"]
                by_repo_count[name] = by_repo_count.get(name, 0) + 1
        if not repos["pageInfo"]["hasNextPage"]:
            break
        after = repos["pageInfo"]["endCursor"]
    return by_bytes, by_repo_count


def compute_streaks(days):
    """Current + longest streak with date ranges, from the fetched window."""
    longest = 0
    longest_range = (None, None)
    current = 0
    run_start = None
    prev_had = False

    for date_str, count in days:
        if count > 0:
            if not prev_had:
                run_start = date_str
            current += 1
            if current > longest:
                longest = current
                longest_range = (run_start, date_str)
            prev_had = True
        else:
            current = 0
            prev_had = False

    # current streak = trailing run ending today (or yesterday, forgivingly)
    trailing = 0
    for date_str, count in reversed(days):
        if count > 0:
            trailing += 1
        else:
            break

    return trailing, longest, longest_range


# ---------------------------------------------------------------------------
# SVG builders — same visual language as the portrait (monospace, one
# fill colour, no gradients/third-party fonts by default).
# ---------------------------------------------------------------------------
def svg_wrap(width, height, body, extra_style=""):
    return (
        f'<svg viewBox="0 0 {width} {height}" width="{width}" height="{height}" '
        f'xmlns="http://www.w3.org/2000/svg">'
        f'<style>text{{font-family:ui-monospace,"JetBrains Mono",monospace;fill:currentColor}}'
        f"{extra_style}</style>{body}</svg>"
    )


def build_hero_stats_svg(total: int, days: list) -> str:
    """Hero total + weekly sparkline — as COLUMNS, not a line.
    A line through sparse daily counts claims values that never existed;
    columns are honest, a zero day is just empty space.
    """
    weekly = []
    for i in range(0, len(days), 7):
        week = days[i : i + 7]
        weekly.append(sum(c for _, c in week))
    weekly = weekly[-52:]

    max_v = max(weekly) if weekly and max(weekly) > 0 else 1
    chart_w, chart_h = 460, 60
    bar_w = chart_w / max(len(weekly), 1)

    bars = ""
    for i, v in enumerate(weekly):
        h = (v / max_v) * chart_h
        x = i * bar_w
        y = chart_h - h
        bars += f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w * 0.7:.1f}" height="{h:.1f}" fill="currentColor" opacity="0.85"/>'

    body = (
        f'<text x="0" y="28" font-size="26">{total}</text>'
        f'<text x="0" y="46" font-size="11" opacity="0.6">contributions, past year</text>'
        f'<g transform="translate(0,60)">{bars}</g>'
    )
    return svg_wrap(chart_w, 130, body)


def build_streak_svg(current: int, longest: int, longest_range) -> str:
    frm, to = longest_range
    body = (
        f'<text x="0" y="24" font-size="20">{current} day current streak</text>'
        f'<text x="0" y="48" font-size="20">{longest} day longest streak</text>'
        f'<text x="0" y="68" font-size="11" opacity="0.6">{frm or "-"} to {to or "-"}</text>'
    )
    return svg_wrap(400, 90, body)


def build_langs_svg(by_bytes: dict, by_repo: dict) -> str:
    top = sorted(by_bytes.items(), key=lambda kv: kv[1], reverse=True)[:6]
    total = sum(v for _, v in top) or 1

    rows = ""
    y = 20
    for name, size in top:
        pct = size / total * 100
        repo_count = by_repo.get(name, 0)
        bar_w = pct * 3.2
        rows += (
            f'<text x="0" y="{y}" font-size="13">{name}</text>'
            f'<rect x="140" y="{y-10}" width="{bar_w:.1f}" height="10" fill="currentColor" opacity="0.85"/>'
            f'<text x="{150 + bar_w:.1f}" y="{y}" font-size="11" opacity="0.6">{pct:.1f}% · {repo_count} repos</text>'
        )
        y += 26
    return svg_wrap(460, y, rows)


def build_year_svg(days: list) -> str:
    """One character per day, using the portrait's own brightness ramp."""
    max_c = max((c for _, c in days), default=1) or 1
    ramp_len = len(RAMP) - 1

    chars = ""
    for date_str, count in days:
        idx = min(ramp_len, int((count / max_c) * ramp_len)) if count else 0
        chars += RAMP[idx] if RAMP[idx] != " " else "."

    # wrap at 52 (weeks) per row for a compact block
    lines = [chars[i : i + 52] for i in range(0, len(chars), 52)]
    body = ""
    for i, line in enumerate(lines):
        y = (i + 1) * 14
        escaped = line.replace("<", "&lt;").replace(">", "&gt;")
        body += f'<text x="0" y="{y}" font-size="12" xml:space="preserve">{escaped}</text>'
    return svg_wrap(52 * 8, len(lines) * 14 + 10, body)


def write_if_changed(path: str, content: str):
    if os.path.exists(path):
        with open(path) as f:
            if f.read() == content:
                return False
    with open(path, "w") as f:
        f.write(content)
    return True


def main():
    login = os.environ["GH_LOGIN"]

    print(f"Fetching contributions for {login}...")
    total, days = fetch_contributions(login)

    print("Fetching languages across public repos...")
    by_bytes, by_repo = fetch_languages(login)

    print("Computing streaks...")
    current, longest, longest_range = compute_streaks(days)

    changed = False
    changed |= write_if_changed("stats.svg", build_hero_stats_svg(total, days))
    changed |= write_if_changed(
        "streak.svg", build_streak_svg(current, longest, longest_range)
    )
    changed |= write_if_changed("langs.svg", build_langs_svg(by_bytes, by_repo))
    changed |= write_if_changed("year.svg", build_year_svg(days))

    print("Changed." if changed else "No change.")


if __name__ == "__main__":
    main()
