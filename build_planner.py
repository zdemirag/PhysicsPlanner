#!/usr/bin/env python3
"""
Refresh the data inside the Physics BA Planner (physics-planner.html).

Run once a year, after the new class schedule is available:

    python build_planner.py --fall FALL.csv --spring SPRING.csv --planner physics-planner.html

What it does
  1. Reads the two BU class-schedule exports (report BU_R0032B_SR_CLASS_SCHD_DOWNLD, CSV).
  2. Collects, for every physics course numbered 100-599 and the math courses the planner
     uses, which term it runs in, its lecture times, instructors, caps and enrollment.
  3. Fetches every BU Hub area page (https://www.bu.edu/hub/hub-courses/) and records the
     Hub units each course carries. Use --hub-cache to reuse a saved copy instead.
  4. Keeps the Hub courses that run in either term, with their titles, terms and times.
  5. Writes all of it into the planner's data block:
         <script id="planner-data" type="application/json"> ... </script>
     Nothing else in the HTML is touched.

Requirements: Python 3.9+, pandas. Fetching Hub pages also needs requests and beautifulsoup4.
    pip install pandas requests beautifulsoup4
"""
import argparse
import datetime
import json
import re
import sys
from pathlib import Path

import pandas as pd

HUB_INDEX = "https://www.bu.edu/hub/hub-courses/"
DAY = {"Mon": "M", "Tue": "T", "Wed": "W", "Thu": "R", "Fri": "F", "Sat": "S", "Sun": "U"}
MATH = ["123", "124", "127", "129", "225", "226", "242", "411", "412", "561"]
ARRANGED_OK = {"401", "402", "491", "492"}  # physics courses that run without set meeting times
MANY_SECTIONS = 12  # Hub courses with more lecture patterns than this skip the clash check
DATA_BLOCK = re.compile(
    r'(<script id="planner-data" type="application/json">)(.*?)(</script>)', re.S)


# ---------------------------------------------------------------- schedule CSVs

def read_schedule(path):
    df = pd.read_csv(path, dtype=str, encoding="latin-1").fillna("")
    need = {"Term", "Subject Area", "Catalog Nbr", "Class Section", "Class Type", "Class Stat",
            "Days Of The Week", "Start Time", "End Time", "Cap Enrl", "Tot Enrl", "Career",
            "Description", "Credit Hours", "Instructor's Last Name"}
    missing = need - set(df.columns)
    if missing:
        sys.exit(f"{path}: missing columns {sorted(missing)}. Is this the class schedule export?")
    terms = df["Term"].unique()
    if len(terms) != 1:
        sys.exit(f"{path}: expected one term, found {list(terms)}")
    return df, terms[0]


def term_label(code):
    """BU term codes: 2 + two-digit year + season digit (8 = fall, 1 = spring). 2268 = Fall 2026."""
    year = 2000 + int(code[1:3])
    season = {"8": "Fall", "1": "Spring"}.get(code[3])
    if not season:
        sys.exit(f"Term {code} is not a fall or spring term.")
    return season, year


def minutes(t):
    m = re.match(r"(\d\d):(\d\d)(AM|PM)", t)
    h, mi, ap = int(m[1]), int(m[2]), m[3]
    if ap == "PM" and h != 12:
        h += 12
    if ap == "AM" and h == 12:
        h = 0
    return h * 60 + mi


def meetings(rows):
    out = []
    for _, r in rows.drop_duplicates(["Days Of The Week", "Start Time", "End Time"]).iterrows():
        if r["Days Of The Week"] and r["Start Time"]:
            out.append(["".join(DAY[x] for x in r["Days Of The Week"].split()),
                        minutes(r["Start Time"]), minutes(r["End Time"])])
    return sorted(out)


def num(x):
    try:
        v = float(x or 0)
        return int(v) if v == int(v) else v
    except ValueError:
        return 0


def course_terms(df, season, keep_detail, require_times=True):
    """Group one term's rows by course. Returns {(subject, catalog): entry}.
    require_times drops courses whose only open sections have no meeting time (often
    "Stop Enrl" placeholders); Hub courses keep them, since online and arranged courses count."""
    out = {}
    for (subj, cat), g in df.groupby(["Subject Area", "Catalog Nbr"]):
        secs, comps = [], {}
        for sec, gs in g.groupby("Class Section"):
            stat = set(gs["Class Stat"])
            if stat <= {"Cancelled"}:
                continue
            m = meetings(gs)
            active = bool(stat & {"Active", "Tentative"})
            if gs["Class Type"].iloc[0] == "Enrollment":
                s = {"s": sec, "m": m, "st": "/".join(sorted(stat))}
                if keep_detail:
                    s["cap"] = num(gs["Cap Enrl"].iloc[0])
                    s["enr"] = num(gs["Tot Enrl"].iloc[0])
                    s["i"] = sorted({x.strip() for x in gs["Instructor's Last Name"] if x.strip()})
                secs.append(s)
            elif active and m:
                comps[sec[0]] = comps.get(sec[0], 0) + 1
        run = [x for x in secs if "Active" in x["st"] or "Tentative" in x["st"]]
        if not run:
            continue
        timed = [x for x in run if x["m"]]
        if require_times and not timed and cat not in ARRANGED_OK:
            continue  # "Stop Enrl" placeholders with no times: not really offered
        for x in run:
            x.pop("st", None)
        out[(subj, cat)] = {"secs": timed or run[:1], "nsec": len(run), "comps": comps,
                            "title": g["Description"].iloc[0].strip(),
                            "cr": num(g["Credit Hours"].iloc[0]), "career": g["Career"].iloc[0]}
    return out


def nice_title(t):
    t = re.sub(r"\s+", " ", t).strip()
    if t.isupper() and len(t) > 4:  # some schedule titles are all caps abbreviations
        t = t.title()
    return t


def short_code(subject, catalog):
    """CASPY + 251 -> 'PY 251'; CFAAR + 121 -> 'CFA AR 121' (CAS prefix dropped, others kept)."""
    college, dept = subject[:3], subject[3:]
    return f"{dept} {catalog}" if college == "CAS" else f"{college} {dept} {catalog}"


# ---------------------------------------------------------------- Hub pages

def fetch_hub(verbose=True):
    """Return {'CAS PH 100': 'units letters', ...} from the live Hub area pages."""
    import requests
    from bs4 import BeautifulSoup

    s = requests.Session()
    s.headers["User-Agent"] = "BU Physics planner data refresh"
    idx = s.get(HUB_INDEX, timeout=60)
    idx.raise_for_status()
    soup = BeautifulSoup(idx.text, "html.parser")
    areas = sorted({a["href"].split("#")[0] for a in soup.select('a[href*="/hub/hub-courses/"]')
                    if re.search(r"/hub/hub-courses/[^/]+/?$", a["href"].split("#")[0])})
    if verbose:
        print(f"Hub: {len(areas)} area pages")
    units, names = {}, {}
    for url in areas:
        r = s.get(url, timeout=120)
        r.raise_for_status()
        cards = parse_hub_cards(r.text, names)
        units.update(cards)
        if verbose:
            print(f"  {url.rstrip('/').split('/')[-1]}: {len(cards)} courses")
    return units, names


def parse_hub_cards(html, names=None):
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    out = {}
    for card in soup.select(".cf-course-card"):
        parts = [card.select_one(c) for c in (".cf-course-college", ".cf-course-dept", ".cf-course-number")]
        if not all(parts):
            continue
        code = " ".join(p.get_text(strip=True) for p in parts)
        letters = []
        for li in card.select(".cf-hub-offerings li"):
            m = re.search(r"cf-hub-area-(\w+)", " ".join(li.get("class", [])))
            if m:
                letters.append(m[1])
                if names is not None:
                    names[m[1]] = li.get_text(strip=True)
        out[code] = "".join(sorted(letters))
    return out


def load_hub_cache(path):
    """Accepts the JSON this script saves, or the compact 'CASAN:211=1AK,...;...' text."""
    text = Path(path).read_text(encoding="utf-8").strip()
    if text.startswith("{"):
        data = json.loads(text)
        return data.get("units", data), data.get("names", {})
    units = {}
    for grp in text.split(";"):
        key, entries = grp.split(":", 1)
        for e in entries.split(","):
            n, u = e.split("=")
            units[f"{key[:3]} {key[3:]} {n}"] = u
    return units, {}


# ---------------------------------------------------------------- build

def build(args):
    fall_df, fall_term = read_schedule(args.fall)
    spring_df, spring_term = read_schedule(args.spring)
    fs, fy = term_label(fall_term)
    ss, sy = term_label(spring_term)
    if fs != "Fall" or ss != "Spring":
        sys.exit("Pass the fall export with --fall and the spring export with --spring.")
    if sy != fy + 1:
        print(f"Warning: Fall {fy} and Spring {sy} are not one academic year.")

    terms = {"F": fall_df, "S": spring_df}

    # Physics and math detail
    sched = {}
    for season, df in terms.items():
        sub = df[((df["Subject Area"] == "CASPY") & df["Catalog Nbr"].str.match(r"^[1-5]\d\d$"))
                 | ((df["Subject Area"] == "CASMA") & df["Catalog Nbr"].isin(MATH))]
        for (subj, cat), e in course_terms(sub, season, keep_detail=True).items():
            code = short_code(subj, cat)
            sched.setdefault(code, {})[season] = {"secs": e["secs"], "nsec": e["nsec"],
                                                  "comps": e["comps"], "title": e["title"]}

    # Hub units
    if args.hub_cache and Path(args.hub_cache).exists() and not args.refresh_hub:
        units, names = load_hub_cache(args.hub_cache)
        print(f"Hub: {len(units)} courses from {args.hub_cache}")
    else:
        units, names = fetch_hub()
        if args.hub_cache:
            Path(args.hub_cache).write_text(json.dumps(
                {"fetched": datetime.date.today().isoformat(), "units": units, "names": names},
                indent=0), encoding="utf-8")
            print(f"Hub: saved {len(units)} courses to {args.hub_cache}")
    if len(units) < 1000:
        print(f"Warning: only {len(units)} Hub courses found. The Hub pages may have changed layout.")

    # Hub courses that run this year (undergraduate, lecture sections)
    hub = {}
    for season, df in terms.items():
        ug = df[df["Career"] == "Undergrad"]
        ug = ug.assign(_hub=(ug["Subject Area"].str[:3] + " " + ug["Subject Area"].str[3:] + " "
                             + ug["Catalog Nbr"]))
        ug = ug[ug["_hub"].isin(units)]
        for (subj, cat), e in course_terms(ug, season, keep_detail=False, require_times=False).items():
            code = short_code(subj, cat)
            h = hub.setdefault(code, {"t": nice_title(e["title"]), "c": e["cr"],
                                      "u": units[f"{subj[:3]} {subj[3:]} {cat}"]})
            pats = sorted({json.dumps(x["m"]) for x in e["secs"] if x["m"]})
            entry = {"nsec": e["nsec"]}
            if len(pats) > MANY_SECTIONS:
                entry["many"] = 1
                entry["secs"] = []
            else:
                entry["secs"] = [{"m": json.loads(p)} for p in pats]
            h[season] = entry

    meta = {"fall": f"Fall {fy}", "spring": f"Spring {sy}", "year": f"{fy}–{str(sy)[2:]}",
            "fallYear": fy, "built": datetime.date.today().isoformat(),
            "hubCourses": len(units), "hubScheduled": len(hub)}
    data = {"meta": meta, "sched": sched, "hub": hub}
    blob = json.dumps(data, separators=(",", ":"), ensure_ascii=False).replace("</", "<\\/")

    html = Path(args.planner).read_text(encoding="utf-8")
    if not DATA_BLOCK.search(html):
        sys.exit(f"{args.planner}: no planner-data block found.")
    html = DATA_BLOCK.sub(lambda m: m[1] + blob + m[3], html, count=1)
    out = Path(args.out or args.planner)
    out.write_text(html, encoding="utf-8")

    # Report
    req = ["PY 251", "PY 252", "PY 351", "PY 355", "PY 405", "PY 406", "PY 408", "PY 410",
           "PY 451", "PY 452", "PY 581", "MA 123", "MA 124", "MA 225"]
    print(f"\n{meta['year']}: {len(sched)} physics/math courses, {len(hub)} Hub courses on the schedule")
    for c in req:
        pat = "".join(s for s in "FS" if s in sched.get(c, {}))
        print(f"  {c}: {'fall & spring' if pat == 'FS' else 'fall' if pat == 'F' else 'spring' if pat == 'S' else 'NOT SCHEDULED'}")
    print(f"\nWrote {out} ({out.stat().st_size // 1024} KB)")


def main():
    p = argparse.ArgumentParser(description="Refresh the Physics BA Planner's schedule and Hub data.")
    p.add_argument("--fall", required=True, help="fall class schedule export (CSV)")
    p.add_argument("--spring", required=True, help="spring class schedule export (CSV)")
    p.add_argument("--planner", required=True, help="planner HTML file to update")
    p.add_argument("--out", help="write here instead of overwriting --planner")
    p.add_argument("--hub-cache", help="saved Hub data: read it if present, otherwise fetch and save it here")
    p.add_argument("--refresh-hub", action="store_true", help="fetch Hub pages even if --hub-cache exists")
    build(p.parse_args())


if __name__ == "__main__":
    main()
