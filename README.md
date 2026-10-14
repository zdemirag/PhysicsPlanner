# Physics BA Planner: yearly data update

The planner is a single HTML file with no server behind it. Everything it knows lives inside the file:

| What | Where it comes from | How it gets updated |
|---|---|---|
| When each course runs, lecture times, instructors, caps, enrollment | BU class schedule exports (CSV, one per term) | `build_planner.py`, every year |
| Hub units for every course, and the list of Hub courses in the finder | BU Hub area pages, https://www.bu.edu/hub/hub-courses/ | `build_planner.py`, every year |
| Year labels ("2026–27", "Fall 2026") | the term codes in the CSVs | `build_planner.py`, every year |
| Physics BA rules, prerequisites, standard sequence, default plan | Bulletin and department pages | by hand, only when the department changes them |
| Each student's plan | their own browser | nothing to do |

The script rewrites only one block in the HTML, `<script id="planner-data" type="application/json">`. All the hand-written rules stay as they are.

## Every year

1. **Export the class schedule.** You need the fall and spring exports of the class schedule report (`BU_R0032B_SR_CLASS_SCHD_DOWNLD`) as CSV files, one per term, in the same format as the 2026–27 files.

2. **Install the tools once:**

   ```
   pip install pandas requests beautifulsoup4
   ```

3. **Run the build:**

   ```
   python build_planner.py --fall FALL.csv --spring SPRING.csv --planner physics-planner.html --hub-cache hub-courses.json
   ```

   - The first run fetches all 21 Hub area pages from bu.edu (about a minute) and saves them to `hub-courses.json`.
   - Later runs reuse that file. Add `--refresh-hub` to fetch fresh Hub data, which you should do once a year.
   - Add `--out new-planner.html` to write a new file instead of overwriting the old one.

4. **Read the summary it prints.** It lists the term every required physics and math course runs in. "NOT SCHEDULED" next to a required course means the export is missing it, or the course isn't running that year. It also warns if fewer than 1,000 Hub courses were found, which would mean the Hub pages changed layout.

5. **Open the HTML in a browser and spot-check it.** Look at the Offerings tab in Faculty view and try the Hub finder. Then share or host the file as before.

### If the script can't fetch the Hub pages

BU may block automated requests. In that case, collect the Hub data in your own browser:

1. Open https://www.bu.edu/hub/hub-courses/ in Chrome or Safari.
2. Open the developer console (View → Developer → JavaScript Console).
3. Paste the snippet below and press Return.

It reads all 21 area pages and downloads `hub-courses.json`. Then run the build as above with `--hub-cache hub-courses.json`.

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

## Hand-edited parts of the planner

Open `physics-planner.html` in a text editor and search for these:

- **Course catalog** (search `C('PY 251'`). One line per physics, math, writing and language course. Each line holds:
  - the title and credits
  - prerequisites (`req`)
  - Hub units (`hub`)
  - the published fall/spring pattern (`off`, used only when a course is missing from the schedule)
  - the standard-sequence term (`nom`, 0 = first fall)
  - notes
- **Major requirements** (search `function majorAudit`). The Graduate Option rules. `PE_EXCLUDE` lists the courses that can't count as the physics elective.
- **Hub requirement counts** (search `const HUB=[`). Units needed in each area for entering first-year students.
- **CAS rules** (search `function casAudit` and `LANG_DONE`). The 128 credits, lab requirement, language requirement, BU residency (68 credits, or 60 for transfers), the 68-credit transfer cap, and the 4 principal physics courses transfers must take in CAS.
- **AP credit chart** (search `const AP_TABLE`). One line per AP exam: the minimum score, the BU course(s) it equals, and the Hub units BU's chart lists. Update it each year from the Registrar's Advanced Credit Guide (https://www.bu.edu/reg/transfer-credit/test-credit/), and change `AP_YEAR`.
- **Hub requirements for transfer students** (search `const REQ_TR`). The 10 requirements transfer students meet with BU courses.
- **Standard four-year plan** (search `function defaultItems`).

## Notes and limits

- Patterns, times and Hub course offerings come from one year of schedules and are assumed to repeat every year. Courses that alternate years will look like they never run in the off year.
- Clash checks use lecture sections only, not discussions or labs. Hub courses with more than 12 different lecture times skip the clash check.
- The Hub finder lists only courses that run in the exported year. Its titles come from the schedule export, which abbreviates some of them.
- Students' saved plans survive a rebuild. A course that stops running shows a "not on the schedule" note.
