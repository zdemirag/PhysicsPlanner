# Physics BA Planner: rules and yearly data

The code in this repository (the planner page, the build script, the transcript reader and the tests) was written by Claude, Anthropic's AI model, working with Zeynep Demiragli, who set the requirements, checked the results against BU's published rules and directed each change.

The planner is a single HTML file with no server behind it. Everything it knows lives inside the file, written there by `build_planner.py`:

| What | Where it comes from | How it gets updated |
|---|---|---|
| Programs (requirements, standard plans), course catalog, Hub, CAS and AP rules | `planner-rules.json`, which you edit | `build_planner.py --rules`, whenever a rule changes |
| When each course runs, lecture times, instructors, caps, enrollment | BU class schedule exports (CSV, one per term) | `build_planner.py`, every year |
| Hub units for every course, and the list of Hub courses in the finder | BU Hub area pages, https://www.bu.edu/hub/hub-courses/ | `build_planner.py`, every year |
| Year labels ("2026–27", "Fall 2026") | the term codes in the CSVs | `build_planner.py`, every year |
| Each student's plan, including an imported transcript | their own browser | nothing to do |

The script rewrites two blocks in the HTML: `<script id="planner-rules" …>` (the rules file) and `<script id="planner-data" …>` (schedule and Hub data). Nothing else changes.

Install the tools once:

```
pip install pandas requests beautifulsoup4
```

## After editing the rules file

```
python build_planner.py --planner physics-planner.html --rules planner-rules.json
```

It checks the file first. It stops on a JSON syntax error, giving the line and column, and it warns about any course named in a requirement, standard plan or prerequisite that isn't in `courses`. Open the HTML afterwards and look at the program's Major tab.

## Every year

1. **Export the class schedule.** You need the fall and spring exports of the class schedule report (`BU_R0032B_SR_CLASS_SCHD_DOWNLD`) as CSV files, one per term, in the same format as the 2026–27 files.

2. **Run the build:**

   ```
   python build_planner.py --planner physics-planner.html --rules planner-rules.json --fall FALL.csv --spring SPRING.csv --hub-cache hub-courses.json --refresh-hub
   ```

   - It fetches all 21 Hub area pages from bu.edu (about a minute) and saves them to `hub-courses.json`. Without `--refresh-hub`, later runs reuse that file.
   - Schedule detail (terms, times, caps) is kept for every physics course numbered 100–599 and every course listed in the rules file.
   - Add `--out new-planner.html` to write a new file instead of overwriting the old one.

3. **Read the summary it prints.** For each program it lists the term each required course runs in. "NOT SCHEDULED" means the export is missing the course, or it isn't running that year. It also warns if fewer than 1,000 Hub courses were found, which would mean the Hub pages changed layout.

4. **Update the year-specific parts of the rules file:** the AP chart (`ap`), and `alternateYears` for courses that run every other year. Then open the HTML and spot-check it: the Offerings tab in Faculty view, the Hub finder, and each program's standard plan.

### If the script can't fetch the Hub pages

BU may block automated requests. In that case, collect the Hub data in your own browser:

1. Open https://www.bu.edu/hub/hub-courses/ in Chrome or Safari.
2. Open the developer console (View → Developer → JavaScript Console).
3. Paste the snippet below and press Return.

It reads all 21 area pages and downloads `hub-courses.json`. Then run the build with `--hub-cache hub-courses.json` and without `--refresh-hub`.

```js
(async () => {
  const idx = new DOMParser().parseFromString(await (await fetch('/hub/hub-courses/')).text(), 'text/html');
  const areas = [...new Set([...idx.querySelectorAll('a[href*="/hub/hub-courses/"]')]
    .map(a => a.href.replace(/#.*$/, '')).filter(h => /\/hub\/hub-courses\/[^/]+\/?$/.test(h)))];
  const units = {}, names = {};
  for (const u of areas) {
    const d = new DOMParser().parseFromString(await (await fetch(u)).text(), 'text/html');
    for (const c of d.querySelectorAll('.cf-course-card')) {
      const id = [...c.querySelectorAll('.cf-course-college,.cf-course-dept,.cf-course-number')].map(x => x.textContent.trim()).join(' ');
      units[id] = [...c.querySelectorAll('.cf-hub-offerings li')].map(li => {
        const L = (li.className.match(/cf-hub-area-(\w+)/) || [])[1]; names[L] = li.textContent.trim(); return L;
      }).sort().join('');
    }
    console.log(u, Object.keys(units).length);
  }
  const blob = new Blob([JSON.stringify({ fetched: new Date().toISOString().slice(0, 10), units, names })], { type: 'application/json' });
  const a = Object.assign(document.createElement('a'), { href: URL.createObjectURL(blob), download: 'hub-courses.json' });
  document.body.append(a); a.click();
})();
```

## The rules file, `planner-rules.json`

It's plain JSON, so keep the quotes and commas exactly as they are; the build script reports the line of any syntax error. It has six sections.

### `programs`

One entry per program, in the order they appear in the planner's Program menu. The first one is the default.

| Field | Meaning |
|---|---|
| `id` | Short internal name, e.g. `"astro"`. Saved plans remember it, so don't change it once in use. |
| `name`, `short` | Full name (page header) and menu label. |
| `sources` | Links shown under the Major tab. |
| `notes` | Lines shown under the Major tab: grade rules, recommended courses. |
| `requirements` | The checklist, in order (below). |
| `standardPlan` | The four-year plan the planner starts from (below). |
| `standardPlanSource` | One sentence saying where the standard plan comes from. |

**Requirements.** Each requirement is one line with a `section` (its heading in the Major tab) and one of three forms:

- **Exact courses:** `"options": [["MA 123","MA 124"], ["MA 127"], ["MA 129"]]`. The first list is the standard choice; the others are allowed substitutes, marked "permitted substitute" when used. Add `"equal": true` when the choices are equal alternatives, such as AS 441 or PY 581.
- **Choose from a list:** `"choose": 2, "from": ["AS 413","AS 414","PY 452"]`.
- **Choose by rule:** `"choose": 1, "match": {"dept": ["PY"], "minLevel": 300, "exclude": ["PY 313", …]}`. Add `"placeholder": "PY ELECTIVE"` to let that placeholder stand in, and `"hint"` for the advice shown while it's missing.

Optional: `"label"` (otherwise the course's own name is used) and `"principal": true` (counts toward the CAS rule that transfer students take at least 4 principal major courses in CAS).

Requirements are checked top to bottom, and a course counts toward only one of them. That's why a "choose by rule" elective comes after the required courses it shouldn't double-count.

**Standard plan.** Each line is `[term, course]` or `[term, course, {details}]`:
- Terms count from 0 (first fall) to 7 (last spring). Term -1 is credit before BU.
- `details` can give a placeholder a `title` and planned `hub` units, or mark AP credit: `{"src": "ap", "exam": "Calculus AB", "hub": ["QR2"]}`.

### `courses`

One line per course the planner knows by name. Any Hub course on the schedule also works when typed in, even if it isn't listed here.

| Field | Meaning |
|---|---|
| `title`, `credits`, `dept` | `dept` sets the color and grouping: PY, AS, MA, WR, LANG, HUB, FREE. |
| `prereqs` | List of requirements, each `"A\|B"` meaning A or B, all taken in an earlier term. |
| `coreqs` | Same, but the same term is also fine. Add `"sameTermNeedsConsent": true` if taking it alongside needs instructor consent. |
| `hub` | Hub units: PIL, AEX, HCO, SI1, SI2, SO1, SO2, QR1, QR2, IIC, GCI, ETR, FYW, WRI, WIN, OSC, DME, CRT, RIL, TWC, CRI. |
| `offered`, `offeredSource` | Published pattern (`"F"`, `"S"`, `"FS"`), used only when the course isn't on the schedule export. |
| `alternateYears` | `"even"` or `"odd"`: the course runs only in academic years starting in an even (or odd) calendar year. AS 413 ran in Fall 2026, so it's `"even"`. |
| `lab` | Counts for the CAS natural science lab requirement. |
| `provides` | Courses this one replaces, e.g. MA 127 provides MA 123 and MA 124. |
| `completesLanguage` | Completes the CAS language requirement. |
| `note` | Shown in the course's details. |
| `placeholder`, `editable`, `multiple`, `display` | For placeholder slots such as `"PY ELECTIVE"` and `"HUB"`. |

### `hub`

`firstYear` (26 units) and `transfer` (10 requirements). For each requirement:
- `units` is how many are needed.
- `tags` lists the Hub units that count toward it.

### `cas`

The CAS numbers, all used as written:
- total credits
- BU credits required, for first-years and for transfers
- the transfer-credit cap
- principal courses that transfers must take in CAS
- the full-time minimum and overload threshold per term
- the courses that complete the language requirement

### `ap`

BU's AP chart. Update it each year from the Registrar's Advanced Credit Guide (https://www.bu.edu/reg/transfer-credit/test-credit/), and change `year`. Each exam has:
- `rules`, by minimum score, each listing the BU courses it equals and the Hub units on the chart. A credit can list `alternatives`, other courses the chart allows in its place (`"course": "PY 251", "alternatives": ["PY 211"]`). The transcript importer uses them to recognize the course the Registrar actually posted.
- Calculus BC only: an `abSubscoreRule`

### Adding another program

Copy a program entry, give it a new `id`, `name` and `short`, and edit its requirements and standard plan. Add any new courses to `courses`, then run the build with `--rules` and with the schedule CSVs, so the new courses get their terms and times. Writing the BA in Physics Interdisciplinary Option this way would take one entry. Its three coordinated courses from the partner department fit a "choose by rule" requirement on that department.

## Student records and transcript import

Each course in a plan can carry a status, set in its details or read from a transcript:

| Status | On the card | Meaning |
|---|---|---|
| Completed | solid card, ✓ and the grade | Counts with its grade. F, W and other no-credit grades earn nothing; C- and below don't count for major courses. |
| In progress | solid card, "In progress" | The current term. |
| Registered | solid card, "Registered" | A later term the student has registered for. The planner fills the rest of that term around it. |
| Planned | dashed outline | Everything else. "Planned" marks courses placed by the automatic planner. |

**Import transcript** (top right) reads a MyBU unofficial transcript saved as a PDF:

- The PDF is read in the browser with pdf.js, loaded from cdnjs.cloudflare.com the first time it's used. Nothing is uploaded, and the name, ID and birth date are ignored.
- It reads the program history (to suggest the program), every term with its courses, credits and grades, test credit (AP), transfer credit, the print date and the cumulative GPA.
- Status comes from the grade and the print date: a grade means completed; no grade means in progress, or registered if the term starts after the print date.
- Summer and winter courses go into that year's spring term, labeled "Summer" or "Winter".
- Courses the planner doesn't know are added as the student's own courses with the transcript's title and credits. Other colleges keep their prefix (`CFA MU 197`).
- AP rows are matched to BU's AP chart by course and exam name, which also sets the AP scores the AP dialog shows and the Hub units each course earns.
- A review table lets you untick rows and correct the program and whether the student started as a first-year or a transfer, before anything changes. Importing replaces the plan in that browser.

The transcript layout is two columns of text, which the reader splits at the middle of the page. If MyBU changes the layout, `parseTranscript()` in the HTML is the place to adjust. Transfer credit has only been tested on the invented sample, so check those rows against the transcript.

**Plan remaining terms** fills the terms after the last completed or in-progress one:

- What's still needed: unmet major requirements, WR 120 and WR 151 (first-years), and the rest of the language sequence.
- Courses that unlock the most others go first, then by their standard-plan term. Each course goes in the earliest term where it runs, its prerequisites are done, its lecture doesn't clash, and the term stays at 16 credits or less.
- Then Hub elective slots for missing Hub units, and free electives until every term is full-time and the total reaches 128.
- Anything that can't be placed is listed with the reason (not offered, prerequisites too late, no room), in the result and in the Issues tab.

Planned courses can be dragged like any other. Running it again replaces its earlier suggestions but keeps courses placed by hand. **Clear planned courses** removes everything not on the transcript from the open terms.

### Tests

`tests/` checks the importer against `sample-transcript.pdf`, an invented student laid out like a MyBU transcript:

```
cd tests
npm install
npm test
```

`make_sample_transcript.py` rewrites the sample (`pip install reportlab`). Never commit a real student's transcript.

## Notes and limits

- Patterns, times and Hub course offerings come from one year of schedules and are assumed to repeat every year. Mark known every-other-year courses with `alternateYears`; any others look like they run every year, or never if they're off in the exported year.
- Clash checks use lecture sections only, not discussions or labs. Hub courses with more than 12 different lecture times skip the clash check.
- The Hub finder lists only courses that run in the exported year. Its titles come from the schedule export, which abbreviates some of them.
- Students' saved plans survive a rebuild. A course that stops running shows a "not on the schedule" note.
- Plan codes (Share / load) carry each course's status and grade, so a plan with an imported transcript can be passed between faculty and student.
- The GPA the planner shows is computed from the grades in the plan. The transcript's GPA is the official one; the import result shows both.
- The Astronomy & Physics standard plan is the planner's own: the Bulletin has no sample schedule for that major.
