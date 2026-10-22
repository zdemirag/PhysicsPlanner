// Checks the transcript importer against tests/sample-transcript.pdf (an invented student).
//   cd tests && npm install && npm test
// It reads the PDF with the same pdf.js version the planner loads in the browser, runs the
// planner page in jsdom, imports the transcript and checks the resulting plan.
const assert = require('assert');
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');
const pdfjs = require('pdfjs-dist/legacy/build/pdf.js');

const ROOT = path.join(__dirname, '..');
const HTML = fs.readFileSync(path.join(ROOT, 'physics-planner.html'), 'utf8');
const PDF = path.join(__dirname, 'sample-transcript.pdf');

// the same text pieces pdfPages() collects in the browser
async function pages(file) {
  const doc = await pdfjs.getDocument({ data: new Uint8Array(fs.readFileSync(file)), isEvalSupported: false, disableFontFace: true, verbosity: 0 }).promise;
  const out = [];
  for (let p = 1; p <= doc.numPages; p++) {
    const pg = await doc.getPage(p), vp = pg.getViewport({ scale: 1 }), tc = await pg.getTextContent();
    out.push({ width: vp.width, items: tc.items.filter(i => i.str && i.str.trim()).map(i => ({ x: i.transform[4], y: i.transform[5], h: Math.hypot(i.transform[2], i.transform[3]), rot: Math.abs(i.transform[1]) > 0.01, s: i.str })) });
  }
  return out;
}

function planner() {
  const dom = new JSDOM('<!doctype html><body>' + HTML + '</body>', {
    runScripts: 'dangerously', url: 'https://planner.test/', pretendToBeVisual: true,
    beforeParse(w) {
      w.HTMLDialogElement.prototype.showModal = function () { this.open = true; };
      w.HTMLDialogElement.prototype.close = function () { this.open = false; this.dispatchEvent(new w.Event('close')); };
    },
  });
  const errors = [];
  dom.window.addEventListener('error', e => errors.push(e.message));
  return { w: dom.window, errors };
}

(async () => {
  const { w, errors } = planner();
  await new Promise(r => setTimeout(r, 50));
  const E = x => w.eval(x);
  w.PAGES = await pages(PDF);

  // 1. what the parser reads
  const R = JSON.parse(E('JSON.stringify(parseTranscript(PAGES),(k,v)=>k==="g"?v.test+"|"+v.subject:v)'));
  assert.strictEqual(R.program, 'B.A. Physics Major');
  assert.strictEqual(R.gpa, 3.21);
  assert.deepStrictEqual(R.terms.map(t => t.label), ['Fall 2025', 'Spring 2026', 'Summer 2 2026', 'Fall 2026', 'Spring 2027']);
  assert.deepStrictEqual(R.terms[0].rows.map(r => `${r.code} ${r.grade}`), ['PY 251 B+', 'MA 124 A-', 'WR 120 A', 'CH 101 W']);
  assert.deepStrictEqual(R.terms[3].rows.map(r => r.code), ['PY 355', 'PY 405', 'WR 151', 'CFA MU 197']);
  assert.strictEqual(R.terms[3].rows[3].cr, 1);
  assert.ok(R.terms.every(t => t.rows.every(r => !/Totals/.test(r.title))), 'totals lines are not titles');
  assert.deepStrictEqual(R.tests.map(r => `${r.g} > ${r.code}`), ['AP|Mathematics: Calculus BC > MA 123', 'AP|Psychology > PS 101']);
  assert.deepStrictEqual(R.transfer.map(r => `${r.code} ${r.cr}`), ['PY 211 4', 'LS 111 4', 'LS 112 4', 'null 8']);

  // 2. the review dialog, then import with automatic planning
  E('openTxReview(parseTranscript(PAGES))');
  const review = w.document.querySelector('#dlgBody').textContent.replace(/\s+/g, ' ');
  assert.match(review, /9 completed, 4 in progress, 2 registered/);
  assert.match(review, /AP Calculus BC \(AB subscore 4\)/);
  assert.strictEqual(E('TX.entry'), 2, 'transfer credit suggests a transfer student');
  w.document.querySelector('[data-txapply]').click();

  const items = JSON.parse(E('JSON.stringify(S.items)'));
  const at = (code, st) => items.filter(i => i.code === code && (st === undefined || i.st === st));
  assert.strictEqual(E('S.program'), 'grad');
  assert.strictEqual(E('S.entry'), 2);
  assert.strictEqual(E('S.start'), 2024);
  assert.deepStrictEqual(JSON.parse(E('JSON.stringify(S.ap)')), { calcbc: 3, calcbc_sub: 4, psych: 4 });
  assert.strictEqual(at('PY 251', 'done')[0].term, 2);
  assert.strictEqual(at('MA 225').length, 2);
  assert.strictEqual(at('MA 225').find(i => i.grade === 'B+').ov.when, 'Summer 2026');
  assert.strictEqual(at('PY 405', 'now')[0].term, 4);
  assert.strictEqual(at('PY 406', 'reg')[0].term, 5);
  assert.ok(at('PY 211')[0].ov.src === 'transfer' && at('PY 211')[0].term === -1);
  assert.strictEqual(at('MA 123')[0].ov.src, 'ap');
  assert.ok(items.some(i => i.code === 'TRCR' && i.ov.cr === 8));
  assert.strictEqual(E('S.custom["CFA MU 197"].cr'), 1);

  // planned courses fill the registered term and the rest; nothing planned in finished terms
  assert.ok(items.filter(i => i.auto).every(i => i.term >= 5 && !i.st));
  assert.ok(items.some(i => i.auto && i.term === 5), 'the registered term is topped up');
  assert.deepStrictEqual(JSON.parse(E('JSON.stringify(majorAudit().filter(x=>!x.met).map(x=>x.label))')), ['PY 581 Advanced Laboratory']);
  assert.ok(JSON.parse(E('JSON.stringify(S.unplaced.map(u=>u.code))')).includes('PY 581'));
  assert.strictEqual(E('buGPA().gpa.toFixed(2)'), '3.21');
  assert.strictEqual(E('analyze().issues.filter(i=>/below the C/.test(i.h)&&i.sev==="err").length'), 0, 'C- retaken in summer');

  // 3. the page shows it
  const terms = [...w.document.querySelectorAll('.term')].map(t => t.querySelector('.th b').textContent);
  assert.ok(terms.includes('Fall 2026In progress') && terms.includes('Spring 2027Registered'));
  assert.ok(w.document.querySelectorAll('.card.planned').length > 0);
  assert.ok(w.document.querySelectorAll('.card.done').length >= 9);

  // 4. plan codes keep the record
  E('openShare()');
  const code = w.document.querySelector('#shOut').value;
  const b = planner();
  await new Promise(r => setTimeout(r, 50));
  b.w.eval('openShare()');
  b.w.document.querySelector('#shIn').value = code;
  b.w.document.querySelector('[data-load]').click();
  const loaded = JSON.parse(b.w.eval('JSON.stringify(S.items.map(i=>[i.code,i.term,i.st||"",i.grade||""]))'));
  assert.deepStrictEqual(loaded, items.map(i => [i.code, i.term, i.st || '', i.grade || '']));
  assert.deepStrictEqual(errors.concat(b.errors), []);
  console.log('transcript import: all checks passed');
})().catch(e => { console.error(e); process.exit(1); });
