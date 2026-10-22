"""Write tests/sample-transcript.pdf: a made-up student's transcript laid out like a
MyBU unofficial transcript (two columns per page, term blocks, test and transfer credit).

Everything in it is invented. It exercises what the planner's importer has to handle:
a transfer student, transfer and AP credit (including a Calculus BC AB-subscore), a
withdrawal, a grade below C, a summer term, a term in progress and a registered term.

    pip install reportlab
    python tests/make_sample_transcript.py
"""
from pathlib import Path
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

OUT = Path(__file__).with_name("sample-transcript.pdf")
W, H = letter
COLS = (37, 318)            # left edge of the left and right columns
TOP, BOTTOM, STEP = 600, 130, 8.2


def term(name, rows):
    """A term block: header, column titles, course rows (dept, number, title, units, grade, points)."""
    out = [("center", name), ("head", None)]
    for r in rows:
        out.append(("row", r))
    earned = sum(u for _, _, _, u, g, _ in rows if g and g not in ("W",))
    out += [("text", "Undergraduate Term Totals"), ("totals", ("Term Totals", "", f"{earned:.1f}", "")), ("gap", None)]
    return out


BLOCKS = [
    ("program", "B.A. Physics Major"),
    ("text", "Beginning of Undergraduate Record"),
    ("gap", None),
    *term("Fall 2025", [("CASPY", "251", "Principles of Physics 1", 4.0, "B+", 13.2),
                        ("CASMA", "124", "Calculus II", 4.0, "A-", 14.8),
                        ("CASWR", "120", "First-Year Writing Seminar", 4.0, "A", 16.0),
                        ("CASCH", "101", "General Chemistry 1", 4.0, "W", 0.0)]),
    *term("Spring 2026", [("CASPY", "252", "Principles of Physics 2", 4.0, "B", 12.0),
                          ("CASMA", "225", "Multivariate Calculus", 4.0, "C-", 6.8),
                          ("CASPY", "313", "Waves and Modern Physics", 4.0, "B-", 10.8),
                          ("CASPH", "100", "Introduction to Philosophy", 4.0, "A", 16.0)]),
    *term("Summer 2 2026", [("CASMA", "225", "Multivariate Calculus", 4.0, "B+", 13.2)]),
    *term("Fall 2026", [("CASPY", "355", "Methods of Theoretical Physics", 4.0, "", 0.0),
                        ("CASPY", "405", "Electromagnetic Fields/Waves 1", 4.0, "", 0.0),
                        ("CASWR", "151", "Writing/Research/Inquiry", 4.0, "", 0.0),
                        ("CFAMU", "197", "ALL CAMPUS ORCH", 1.0, "", 0.0)]),
    *term("Spring 2027", [("CASPY", "406", "Electromagnetic Fields/Waves 2", 4.0, "", 0.0),
                          ("CASPY", "451", "Quantum Physics 1", 4.0, "", 0.0)]),
    ("career", ("Cumulative Totals", "3.21", "32.0", "102.8")),
    ("gap", None),
    ("section", "TRANSFER CREDIT"),
    ("text", "Example Community College"),
    ("trhead", None),
    ("tr", ("CASPY", "211", "General Physics 1", "4.00")),
    ("tr", ("CASLS", "111", "First-Semester Spanish", "4.00")),
    ("tr", ("CASLS", "112", "Second-Semester Spanish", "4.00")),
    ("tr", ("CASXX", "1XX", "General Elective", "8.00")),
    ("gap", None),
    ("section", "TEST CREDIT"),
    ("testhead", None),
    ("test", ("AP", ["Mathematics:", "Calculus BC"], "CASMA", "123", ["Calculus 1"], "4.00")),
    ("test", ("AP", ["Psychology"], "CASPS", "101", ["General Psychology"], "4.00")),
    ("text", "End of Undergraduate Record"),
]


def lines_for(block):
    """One block -> list of lines; each line is a list of (x offset in the column, text)."""
    kind, v = block
    if kind == "program":
        return [[(66, v)]]
    if kind == "text":
        return [[(0, v)]]
    if kind == "gap":
        return [[]]
    if kind == "center":
        return [[(112, v)]]
    if kind == "section":
        return [[(103, v)]]
    if kind == "head":
        return [[(0, "Course"), (57, "Title"), (149, "Units"), (178, "Grade"), (224, "Grade")], [(224, "Points")]]
    if kind == "row":
        d, n, t, u, g, p = v
        line = [(0, d), (32, n), (57, t), (155, f"{u:.1f}")]
        if g:
            line.append((184, g))
        line.append((229, f"{p:.1f}"))
        return [line]
    if kind == "totals":
        return [[(0, v[0]), (149, v[2])]]
    if kind == "career":
        return [[(0, v[0]), (86, v[1]), (152, v[2]), (229, v[3])]]
    if kind == "trhead":
        return [[(0, "Course"), (60, "Title"), (215, "Units")]]
    if kind == "tr":
        d, n, t, u = v
        return [[(0, d), (30, n), (60, t), (220, u)]]
    if kind == "testhead":
        return [[(1, "Test"), (27, "Subject"), (92, "Course"), (155, "Title"), (229, "Credits")]]
    if kind == "test":
        test, subj, d, n, title, cr = v
        out = [[(1, test), (27, subj[0]), (92, d), (122, n), (155, title[0]), (235, cr)]]
        for extra in subj[1:]:
            out.append([(27, extra)])
        return out
    raise ValueError(kind)


def header(c, page, pages):
    c.setFont("Helvetica", 7)
    c.drawString(468, 726, "DATE PRINTED: 10/22/2026")
    c.drawString(468, 711, f"Page {page} of {pages}")
    c.setFont("Helvetica-Bold", 12)
    c.drawString(118, 721, "Boston University Unofficial Transcript")
    c.setFont("Helvetica", 9)
    c.drawString(36, 659, "STUDENT NAME")
    c.drawString(260, 659, "BOSTON UNIVERSITY ID")
    c.drawString(36, 648, "Sample Student")
    c.drawString(289, 648, "U00000000")
    c.setFont("Helvetica", 7)
    c.drawString(37, 103, "This is an unofficial transcript and is not official without the authorized signature and seal of the University.")
    c.saveState()
    c.setFont("Helvetica", 106)
    c.setFillGray(0.93)
    c.translate(136, 143)
    c.rotate(55)
    c.drawString(0, 0, "unofficial")
    c.restoreState()


def main():
    lines = [ln for b in BLOCKS for ln in lines_for(b)]
    per_col = int((TOP - BOTTOM) / STEP)
    cols = [lines[i:i + per_col] for i in range(0, len(lines), per_col)]
    pages = (len(cols) + 1) // 2
    c = canvas.Canvas(str(OUT), pagesize=letter)
    c.setTitle("Sample unofficial transcript (invented)")
    for p in range(pages):
        header(c, p + 1, pages)
        c.setFont("Helvetica", 7)
        for side in (0, 1):
            k = 2 * p + side
            if k >= len(cols):
                break
            y = TOP
            for ln in cols[k]:
                for dx, text in ln:
                    c.drawString(COLS[side] + dx, y, text)
                y -= STEP
        c.showPage()
    c.save()
    print(f"Wrote {OUT} ({pages} pages)")


if __name__ == "__main__":
    main()
