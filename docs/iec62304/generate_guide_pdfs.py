"""
Generate premium PDF versions of IEC 62304 compliance documents.

MSTool-AI — IEC 62304 Class C Medical Device Software
Documents: CLAUDE.md (Development Guidelines) + TEAM_GUIDE (GUIDE-001)

Design: Navy/teal medical-grade aesthetic with iconography, section badges,
callout boxes, and professional typography matching the template suite.
"""

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.colors import HexColor, white, Color
from reportlab.lib.units import mm
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, Flowable, KeepTogether, PageBreak,
)
from reportlab.graphics.shapes import Drawing, Rect, Circle, Line, String, Group
from reportlab.graphics import renderPDF
import os
from datetime import datetime

# ─── Premium Color Palette ───
NAVY = HexColor('#0F172A')
NAVY_LIGHT = HexColor('#1E293B')
TEAL = HexColor('#0D9488')
TEAL_LIGHT = HexColor('#14B8A6')
TEAL_BG = HexColor('#F0FDFA')
BLUE = HexColor('#2563EB')
BLUE_LIGHT = HexColor('#3B82F6')
BLUE_BG = HexColor('#EFF6FF')
RED = HexColor('#DC2626')
RED_BG = HexColor('#FEF2F2')
RED_LIGHT = HexColor('#FCA5A5')
AMBER = HexColor('#D97706')
AMBER_BG = HexColor('#FFFBEB')
GREEN = HexColor('#059669')
GREEN_BG = HexColor('#ECFDF5')
PURPLE = HexColor('#7C3AED')
PURPLE_BG = HexColor('#F5F3FF')
LIGHT_BG = HexColor('#F8FAFC')
FILL_BG = HexColor('#F1F5F9')
MED_GRAY = HexColor('#94A3B8')
DARK_GRAY = HexColor('#334155')
BORDER = HexColor('#E2E8F0')
TABLE_HEADER = HexColor('#1E3A5F')
TABLE_ALT = HexColor('#F8FAFC')
WHITE = white

PAGE_W, PAGE_H = A4
MARGIN = 18 * mm
CONTENT_W = PAGE_W - 2 * MARGIN
OUTPUT_DIR = os.path.dirname(__file__)
NOW = datetime.now().strftime("%Y-%m-%d")


# ─── Styles ───
def S(name, **kw):
    d = dict(fontName='Helvetica', fontSize=9, textColor=DARK_GRAY, leading=12)
    d.update(kw)
    return ParagraphStyle(name, **d)

ST = {
    'doc_title': S('dt', fontName='Helvetica-Bold', fontSize=20, textColor=NAVY, alignment=TA_CENTER, spaceAfter=2, leading=24),
    'doc_subtitle': S('dsubt', fontName='Helvetica', fontSize=11, textColor=TEAL, alignment=TA_CENTER, spaceAfter=6, leading=14),
    'title': S('t', fontName='Helvetica-Bold', fontSize=15, textColor=NAVY, alignment=TA_CENTER, spaceAfter=2),
    'subtitle': S('st', fontSize=9, textColor=MED_GRAY, alignment=TA_CENTER, spaceAfter=10),
    'section': S('sec', fontName='Helvetica-Bold', fontSize=12, textColor=NAVY, spaceBefore=14, spaceAfter=6, leading=15),
    'subsection': S('ss', fontName='Helvetica-Bold', fontSize=10, textColor=TEAL, spaceBefore=10, spaceAfter=4, leading=13),
    'step_title': S('stp', fontName='Helvetica-Bold', fontSize=9.5, textColor=NAVY_LIGHT, spaceBefore=8, spaceAfter=3, leading=12),
    'body': S('b', fontSize=8.5, textColor=DARK_GRAY, spaceAfter=3, leading=12),
    'body_indent': S('bi', fontSize=8.5, textColor=DARK_GRAY, spaceAfter=3, leading=12, leftIndent=12),
    'small': S('sm', fontSize=7, textColor=MED_GRAY, leading=9),
    'th': S('th', fontName='Helvetica-Bold', fontSize=7.5, textColor=white, leading=10),
    'td': S('td', fontSize=7.5, textColor=DARK_GRAY, leading=10),
    'td_bold': S('tdb', fontName='Helvetica-Bold', fontSize=7.5, textColor=DARK_GRAY, leading=10),
    'label': S('lb', fontName='Helvetica-Bold', fontSize=8, textColor=HexColor('#475569')),
    'check': S('ck', fontSize=8.5, textColor=DARK_GRAY, leading=13),
    'code': S('cd', fontName='Courier', fontSize=7.5, textColor=NAVY_LIGHT, leading=10, leftIndent=6),
    'code_indent': S('cdi', fontName='Courier', fontSize=7, textColor=NAVY_LIGHT, leading=9.5, leftIndent=14),
    'callout_title': S('ct', fontName='Helvetica-Bold', fontSize=9, textColor=NAVY, leading=12),
    'callout_body': S('cb', fontSize=8.5, textColor=DARK_GRAY, leading=12),
    'badge_text': S('bt', fontName='Helvetica-Bold', fontSize=7, textColor=white, leading=9),
    'toc_entry': S('toc', fontSize=9, textColor=BLUE, leading=16, leftIndent=8),
}


# ─── Custom Flowables ───

class SectionBadge(Flowable):
    """Numbered section badge with icon-style circle."""
    def __init__(self, number, title, color=TEAL, width=None):
        Flowable.__init__(self)
        self.number = str(number)
        self.title_text = title
        self.color = color
        self.width = width or CONTENT_W
        self.height = 28

    def draw(self):
        # Circle badge
        self.canv.setFillColor(self.color)
        self.canv.circle(14, 14, 12, fill=1, stroke=0)
        self.canv.setFillColor(white)
        self.canv.setFont('Helvetica-Bold', 12)
        tw = self.canv.stringWidth(self.number, 'Helvetica-Bold', 12)
        self.canv.drawString(14 - tw/2, 9, self.number)
        # Title
        self.canv.setFillColor(NAVY)
        self.canv.setFont('Helvetica-Bold', 13)
        self.canv.drawString(32, 8, self.title_text)
        # Underline accent
        title_w = self.canv.stringWidth(self.title_text, 'Helvetica-Bold', 13)
        self.canv.setStrokeColor(self.color)
        self.canv.setLineWidth(2)
        self.canv.line(32, 4, 32 + title_w, 4)


class CalloutBox(Flowable):
    """Colored callout/alert box with left border accent."""
    def __init__(self, title, body_lines, accent_color=BLUE, bg_color=BLUE_BG, width=None, icon_char=None):
        Flowable.__init__(self)
        self.title_text = title
        self.body_lines = body_lines
        self.accent = accent_color
        self.bg = bg_color
        self.box_width = width or CONTENT_W
        self.icon_char = icon_char or '!'
        self.width = self.box_width
        line_count = len(body_lines) if body_lines else 0
        self.height = max(40, 24 + line_count * 13)

    def draw(self):
        c = self.canv
        h = self.height
        w = self.box_width
        # Background
        c.setFillColor(self.bg)
        c.roundRect(0, 0, w, h, 4, fill=1, stroke=0)
        # Left accent bar
        c.setFillColor(self.accent)
        c.roundRect(0, 0, 4, h, 2, fill=1, stroke=0)
        # Icon circle
        c.setFillColor(self.accent)
        c.circle(18, h - 15, 8, fill=1, stroke=0)
        c.setFillColor(white)
        c.setFont('Helvetica-Bold', 9)
        iw = c.stringWidth(self.icon_char, 'Helvetica-Bold', 9)
        c.drawString(18 - iw/2, h - 18, self.icon_char)
        # Title
        c.setFillColor(NAVY)
        c.setFont('Helvetica-Bold', 9)
        c.drawString(32, h - 18, self.title_text)
        # Body lines
        c.setFillColor(DARK_GRAY)
        c.setFont('Helvetica', 8)
        y = h - 32
        for line in self.body_lines:
            if y < 4:
                break
            c.drawString(14, y, line)
            y -= 12


class StepNumber(Flowable):
    """Inline step number badge."""
    def __init__(self, number, text, color=TEAL):
        Flowable.__init__(self)
        self.number = str(number)
        self.text = text
        self.color = color
        self.width = CONTENT_W
        self.height = 20

    def draw(self):
        c = self.canv
        # Small badge
        c.setFillColor(self.color)
        c.roundRect(0, 4, 20, 14, 3, fill=1, stroke=0)
        c.setFillColor(white)
        c.setFont('Helvetica-Bold', 8)
        nw = c.stringWidth(self.number, 'Helvetica-Bold', 8)
        c.drawString(10 - nw/2, 7, self.number)
        # Text
        c.setFillColor(NAVY_LIGHT)
        c.setFont('Helvetica-Bold', 9.5)
        c.drawString(26, 7, self.text)


class CheckItem(Flowable):
    """Styled checkbox item."""
    def __init__(self, text, width=None, indent=0):
        Flowable.__init__(self)
        self.text = text
        self.item_width = width or CONTENT_W
        self.indent = indent
        self.width = self.item_width
        self.height = 15

    def draw(self):
        c = self.canv
        x = self.indent
        # Box
        c.setStrokeColor(TEAL)
        c.setFillColor(TEAL_BG)
        c.setLineWidth(0.6)
        c.roundRect(x, 3, 10, 10, 1.5, fill=1, stroke=1)
        # Text
        c.setFillColor(DARK_GRAY)
        c.setFont('Helvetica', 8)
        # Truncate if too long
        max_chars = int((self.item_width - x - 20) / 3.5)
        txt = self.text[:max_chars] if len(self.text) > max_chars else self.text
        c.drawString(x + 15, 4, txt)


class CodeBlock(Flowable):
    """Styled code block with dark background."""
    def __init__(self, lines, width=None):
        Flowable.__init__(self)
        self.lines = lines
        self.box_width = width or (CONTENT_W - 8)
        self.width = self.box_width + 8
        self.height = max(20, 10 + len(lines) * 11)

    def draw(self):
        c = self.canv
        h = self.height
        w = self.box_width
        # Background
        c.setFillColor(HexColor('#1E293B'))
        c.roundRect(4, 0, w, h, 4, fill=1, stroke=0)
        # Code text
        c.setFillColor(HexColor('#A5F3FC'))
        c.setFont('Courier', 7)
        y = h - 12
        for line in self.lines:
            if y < 2:
                break
            c.drawString(12, y, line[:95])
            y -= 11


class GradientBar(Flowable):
    """Horizontal gradient bar for visual separation."""
    def __init__(self, width=None, height=3):
        Flowable.__init__(self)
        self.bar_width = width or CONTENT_W
        self.width = self.bar_width
        self.height = height

    def draw(self):
        c = self.canv
        steps = 40
        w = self.bar_width / steps
        for i in range(steps):
            frac = i / steps
            r = 0.051 * (1 - frac) + 0.051 * frac
            g = 0.580 * (1 - frac) + 0.090 * frac
            b = 0.533 * (1 - frac) + 0.910 * frac
            c.setFillColor(Color(r, g, b))
            c.rect(i * w, 0, w + 0.5, self.height, fill=1, stroke=0)


class InfoRow(Flowable):
    """Key-value info row with label and value."""
    def __init__(self, pairs, width=None):
        Flowable.__init__(self)
        self.pairs = pairs
        self.row_width = width or CONTENT_W
        self.width = self.row_width
        self.height = 18

    def draw(self):
        c = self.canv
        n = len(self.pairs)
        col_w = self.row_width / n
        x = 0
        for label, value in self.pairs:
            c.setFillColor(MED_GRAY)
            c.setFont('Helvetica', 6.5)
            c.drawString(x, 10, label)
            c.setFillColor(NAVY)
            c.setFont('Helvetica-Bold', 8.5)
            c.drawString(x, 0, value)
            x += col_w


# ─── Utility Functions ───

def table(headers, rows, col_widths=None):
    hc = [Paragraph(h, ST['th']) for h in headers]
    data = [hc] + [[Paragraph(str(c), ST['td']) for c in r] for r in rows]
    if not col_widths:
        col_widths = [CONTENT_W / len(headers)] * len(headers)
    t = Table(data, colWidths=col_widths, repeatRows=1)
    cmds = [
        ('BACKGROUND', (0, 0), (-1, 0), TABLE_HEADER),
        ('TEXTCOLOR', (0, 0), (-1, 0), white),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ('GRID', (0, 0), (-1, -1), 0.4, BORDER),
        ('LINEBELOW', (0, 0), (-1, 0), 1.2, TEAL),
    ]
    for i in range(2, len(data), 2):
        cmds.append(('BACKGROUND', (0, i), (-1, i), TABLE_ALT))
    t.setStyle(TableStyle(cmds))
    return t


def table_colored_first_col(headers, rows, col_widths=None, first_col_color=NAVY):
    """Table where first column cells are bold and colored."""
    hc = [Paragraph(h, ST['th']) for h in headers]
    data_rows = []
    for r in rows:
        row = [Paragraph(str(r[0]), ST['td_bold'])] + [Paragraph(str(c), ST['td']) for c in r[1:]]
        data_rows.append(row)
    data = [hc] + data_rows
    if not col_widths:
        col_widths = [CONTENT_W / len(headers)] * len(headers)
    t = Table(data, colWidths=col_widths, repeatRows=1)
    cmds = [
        ('BACKGROUND', (0, 0), (-1, 0), TABLE_HEADER),
        ('TEXTCOLOR', (0, 0), (-1, 0), white),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ('GRID', (0, 0), (-1, -1), 0.4, BORDER),
        ('LINEBELOW', (0, 0), (-1, 0), 1.2, TEAL),
    ]
    for i in range(2, len(data), 2):
        cmds.append(('BACKGROUND', (0, i), (-1, i), TABLE_ALT))
    t.setStyle(TableStyle(cmds))
    return t


def hf_guide(canvas, doc, title, doc_id):
    """Premium header and footer for guide documents."""
    canvas.saveState()
    # Header bar
    canvas.setFillColor(NAVY)
    canvas.rect(0, PAGE_H - 13 * mm, PAGE_W, 13 * mm, fill=1, stroke=0)
    # Teal accent line
    canvas.setFillColor(TEAL)
    canvas.rect(0, PAGE_H - 13.6 * mm, PAGE_W, 0.6 * mm, fill=1, stroke=0)
    # Header text
    canvas.setFillColor(white)
    canvas.setFont('Helvetica-Bold', 10)
    canvas.drawString(MARGIN, PAGE_H - 9.5 * mm, 'MSTool-AI')
    canvas.setFont('Helvetica', 7.5)
    canvas.setFillColor(HexColor('#94A3B8'))
    canvas.drawString(MARGIN + 55 * mm, PAGE_H - 9.5 * mm, 'IEC 62304 Class C Medical Device Software')
    canvas.setFillColor(TEAL_LIGHT)
    canvas.setFont('Helvetica-Bold', 7.5)
    canvas.drawRightString(PAGE_W - MARGIN, PAGE_H - 9.5 * mm, f'{doc_id}  |  v1.0')
    # Footer
    canvas.setFillColor(NAVY)
    canvas.rect(0, 0, PAGE_W, 10 * mm, fill=1, stroke=0)
    canvas.setFillColor(TEAL)
    canvas.rect(0, 10 * mm, PAGE_W, 0.4 * mm, fill=1, stroke=0)
    canvas.setFillColor(HexColor('#64748B'))
    canvas.setFont('Helvetica', 6)
    canvas.drawString(MARGIN, 4 * mm,
                      'IEC 62304:2006+A1:2015  |  ISO 14971:2019  |  IEC 81001-5-1:2021  |  EU MDR 2017/745  |  CONFIDENTIAL')
    canvas.setFillColor(white)
    canvas.setFont('Helvetica-Bold', 7)
    canvas.drawRightString(PAGE_W - MARGIN, 4 * mm, f'Page {doc.page}')
    canvas.restoreState()


# ═══════════════════════════════════════════════════════════════
# DOCUMENT 1: CLAUDE.md → Development Guidelines PDF
# ═══════════════════════════════════════════════════════════════

def generate_claude_md_pdf():
    path = os.path.join(OUTPUT_DIR, 'MSTool-AI_Development_Guidelines.pdf')
    doc = SimpleDocTemplate(path, pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN,
                            topMargin=20 * mm, bottomMargin=16 * mm,
                            title='MSTool-AI Development Guidelines')
    s = []

    # ─── Cover Section ───
    s.append(Spacer(1, 30))
    s.append(GradientBar())
    s.append(Spacer(1, 15))
    s.append(Paragraph('MSTool-AI', ST['doc_title']))
    s.append(Paragraph('Development Guidelines', ST['doc_subtitle']))
    s.append(Spacer(1, 4))
    s.append(InfoRow([
        ('Document ID', 'DEV-GUIDE-001'),
        ('Version', '1.0'),
        ('Date', 'April 12, 2026'),
        ('Classification', 'IEC 62304 Class C'),
    ]))
    s.append(Spacer(1, 8))
    s.append(GradientBar())
    s.append(Spacer(1, 10))

    # ─── Critical Warning ───
    s.append(CalloutBox(
        'CRITICAL — READ BEFORE CONTRIBUTING',
        [
            'This project is IEC 62304 Class C — the highest software safety class.',
            'A software failure could contribute to DEATH or SERIOUS INJURY.',
            'Every code change must follow these guidelines without exception.',
            'Violations will result in audit findings and potential regulatory action.',
        ],
        accent_color=RED, bg_color=RED_BG, icon_char='!'
    ))
    s.append(Spacer(1, 10))

    # ─── Section 1: Before Writing Code ───
    s.append(SectionBadge('1', 'Before Writing Any Code', TEAL))
    s.append(Spacer(1, 6))

    s.append(StepNumber('1', 'Check the Requirement'))
    s.append(Paragraph(
        'Every change must trace to a requirement in <b>SRS-001</b> '
        '(<font face="Courier" size="7">docs/iec62304/02_Software_Requirements_Specification.md</font>). '
        'If no requirement exists, <b>create one first</b>.',
        ST['body_indent']))

    s.append(StepNumber('2', 'Check the Risk'))
    s.append(Paragraph(
        'If your change touches a Class C module (see Section 2), review <b>RMF-001</b> '
        '(<font face="Courier" size="7">docs/iec62304/03_Risk_Management_File.md</font>) for related hazards.',
        ST['body_indent']))

    s.append(StepNumber('3', 'Never Skip Code Review'))
    s.append(CalloutBox(
        'Mandatory Rule',
        ['Never modify a Class C module without a formal code review — no exceptions.'],
        accent_color=AMBER, bg_color=AMBER_BG, icon_char='!'
    ))
    s.append(Spacer(1, 6))

    # ─── Section 2: Class C Modules ───
    s.append(SectionBadge('2', 'Class C Modules', RED))
    s.append(Spacer(1, 4))
    s.append(Paragraph(
        'The following modules are classified as <b>Software Safety Class C</b> — '
        'the highest safety class under IEC 62304. Extra care, mandatory review, '
        'and full traceability are required for any change.',
        ST['body']))
    s.append(Spacer(1, 4))

    modules = [
        ['ai_segmentation_service.py', 'backend/app/services/', 'AI-driven brain segmentation (Vertex AI proxy)'],
        ['brain_volumetry_service.py', 'backend/app/services/', 'Brain structure volume computation'],
        ['brain_report_service.py', 'backend/app/services/', 'Clinical report generation (Claude API)'],
        ['lesion_analysis_service.py', 'backend/app/services/', 'MS lesion analysis + DIS criteria'],
        ['ms_region_classifier.py', 'backend/app/services/', 'MAGNIMS region classification (PV/JC/IT/DWM)'],
        ['nifti_utils.py', 'backend/app/utils/', 'NIfTI file processing + orientation'],
        ['dicom_utils.py', 'backend/app/utils/', 'DICOM parsing + DICOM-SEG export'],
        ['edgeAI.worker.ts', 'frontend/src/workers/', 'Browser ONNX inference (screening)'],
    ]
    s.append(table(
        ['Module', 'Path', 'Function'],
        modules,
        col_widths=[48 * mm, 38 * mm, 76 * mm]
    ))
    s.append(Spacer(1, 6))

    # ─── Section 3: PR Requirements ───
    s.append(SectionBadge('3', 'Pull Request Requirements', BLUE))
    s.append(Spacer(1, 6))
    s.append(Paragraph('Every pull request <b>MUST</b> include:', ST['body']))
    s.append(Spacer(1, 3))
    s.append(CheckItem('Description of what changed and WHY'))
    s.append(CheckItem('Reference to requirement ID (e.g., "Implements REQ-FUNC-040")'))
    s.append(CheckItem('If safety-related: reference to hazard ID (e.g., "Risk control for HAZ-002")'))
    s.append(CheckItem('All CI checks must pass before merge'))
    s.append(CheckItem('At least 1 code review approval'))
    s.append(CheckItem('For Class C changes: at least 2 code review approvals'))
    s.append(Spacer(1, 4))

    s.append(CalloutBox(
        'CI Pipeline Checks (all must be GREEN)',
        [
            'TypeScript compilation (npx tsc --noEmit)',
            'Frontend build (npm run build)',
            'Backend tests (python -m pytest)',
            'SOUP vulnerability scan (npm audit + pip-audit)',
            'Python syntax verification (ast.parse)',
        ],
        accent_color=GREEN, bg_color=GREEN_BG, icon_char='✓'
    ))
    s.append(Spacer(1, 6))

    # ─── Section 4: After Deploying ───
    s.append(SectionBadge('4', 'After Deploying', PURPLE))
    s.append(Spacer(1, 6))
    s.append(Paragraph(
        'After every deployment, run the endpoint verification script. <b>All 9 checks must PASS.</b>',
        ST['body']))
    s.append(Spacer(1, 4))
    s.append(CodeBlock([
        'bash test_endpoints.sh',
        '',
        '# Expected output:',
        'Check 1: Health endpoint .............. PASS',
        'Check 2: Auth login ................... PASS',
        'Check 3: File upload .................. PASS',
        '...',
        'Check 9: AI segmentation .............. PASS',
        '',
        'Result: 9/9 PASS — deployment verified',
    ]))
    s.append(Spacer(1, 6))

    # ─── Section 5: Templates ───
    s.append(SectionBadge('5', 'Templates & Records', TEAL))
    s.append(Spacer(1, 6))
    s.append(Paragraph(
        'Fillable PDF audit evidence forms are in <font face="Courier" size="7.5">'
        'docs/iec62304/templates/</font>. Use them for every code review, test, release, and risk verification.',
        ST['body']))
    s.append(Spacer(1, 4))
    s.append(table(
        ['Template', 'ID', 'When to Use'],
        [
            ['Problem Report', 'TPL-01', 'When a bug is found'],
            ['Release Checklist', 'TPL-02', 'Before every deployment'],
            ['Code Review Checklist', 'TPL-03', 'For every PR review'],
            ['Risk Control Verification', 'TPL-04', 'Verifying risk controls'],
            ['Design Review Record', 'TPL-05', 'Architecture/design reviews'],
            ['Test Execution Report', 'TPL-06', 'Testing requirements'],
            ['SOUP Vulnerability Review', 'TPL-07', 'Monthly dependency check'],
            ['Serious Incident Report', 'TPL-08', 'Safety incidents'],
            ['Change Control Record', 'TPL-09', 'Significant code changes'],
            ['Quality Gate Approval', 'TPL-10', 'Phase gate approvals'],
            ['Document Approval Record', 'TPL-11', 'Formal document sign-off'],
        ],
        col_widths=[44 * mm, 18 * mm, 100 * mm]
    ))
    s.append(Spacer(1, 8))

    # ─── Section 6: Coding Standards ───
    s.append(SectionBadge('6', 'Coding Standards', NAVY_LIGHT))
    s.append(Spacer(1, 6))
    s.append(table(
        ['Language', 'Standard', 'Enforcement'],
        [
            ['TypeScript', 'ESLint rules + TypeScript strict mode', 'CI pipeline (npx tsc --noEmit)'],
            ['Python', 'PEP 8 + type annotations', 'CI pipeline (ast.parse + syntax check)'],
        ],
        col_widths=[30 * mm, 60 * mm, 72 * mm]
    ))
    s.append(Spacer(1, 6))
    s.append(Paragraph('<b>Commit message format:</b>', ST['body']))
    s.append(CodeBlock([
        'feat(REQ-FUNC-040): Implement volume computation',
        '',
        'Implements voxel counting with normative percentile comparison.',
        'Risk control RC-004 (volumetry displays percentile ranges).',
        'Unit test: UT-VOL-001',
    ]))
    s.append(Spacer(1, 6))

    # ─── References ───
    s.append(SectionBadge('7', 'Regulatory References', MED_GRAY))
    s.append(Spacer(1, 6))
    s.append(table(
        ['Standard', 'Title', 'Relevance'],
        [
            ['IEC 62304:2006+A1:2015', 'Medical device software — Software life cycle processes', 'Primary lifecycle standard'],
            ['ISO 14971:2019', 'Medical devices — Application of risk management', 'Risk management framework'],
            ['IEC 81001-5-1:2021', 'Health software — Security for health IT products', 'Cybersecurity requirements'],
            ['EU MDR 2017/745', 'European Medical Device Regulation', 'Market access regulation'],
            ['EU AI Act 2024/1689', 'Artificial Intelligence Act', 'AI-specific requirements'],
        ],
        col_widths=[38 * mm, 65 * mm, 59 * mm]
    ))

    # ─── Footer ───
    s.append(Spacer(1, 14))
    s.append(GradientBar())
    s.append(Spacer(1, 6))
    s.append(Paragraph(
        f'MSTool-AI Development Guidelines  |  DEV-GUIDE-001 v1.0  |  Generated {NOW}  |  CONFIDENTIAL',
        ST['small']))

    doc.build(s,
              onFirstPage=lambda c, d: hf_guide(c, d, 'Development Guidelines', 'DEV-GUIDE-001'),
              onLaterPages=lambda c, d: hf_guide(c, d, 'Development Guidelines', 'DEV-GUIDE-001'))
    print(f'  OK MSTool-AI_Development_Guidelines.pdf')


# ═══════════════════════════════════════════════════════════════
# DOCUMENT 2: TEAM_GUIDE → Team Operating Guide PDF
# ═══════════════════════════════════════════════════════════════

def generate_team_guide_pdf():
    path = os.path.join(OUTPUT_DIR, 'MSTool-AI_Team_Guide_IEC62304.pdf')
    doc = SimpleDocTemplate(path, pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN,
                            topMargin=20 * mm, bottomMargin=16 * mm,
                            title='MSTool-AI Team Operating Guide for IEC 62304 Compliance')
    s = []

    # ─── Cover ───
    s.append(Spacer(1, 25))
    s.append(GradientBar(height=4))
    s.append(Spacer(1, 18))
    s.append(Paragraph('MSTool-AI', ST['doc_title']))
    s.append(Paragraph('Team Operating Guide', ST['doc_subtitle']))
    s.append(Paragraph('IEC 62304 Class C Compliance', S('csub', fontName='Helvetica-Bold',
                        fontSize=10, textColor=RED, alignment=TA_CENTER, spaceAfter=10)))
    s.append(Spacer(1, 6))
    s.append(InfoRow([
        ('Document ID', 'GUIDE-001'),
        ('Version', '1.0'),
        ('Date', 'April 12, 2026'),
        ('Audience', 'ALL Team Members'),
    ]))
    s.append(Spacer(1, 10))
    s.append(GradientBar(height=4))
    s.append(Spacer(1, 12))

    # ─── Critical Warning ───
    s.append(CalloutBox(
        'CRITICAL SAFETY NOTICE',
        [
            'MSTool-AI is classified as IEC 62304 Software Safety Class C — the HIGHEST safety class.',
            'A software failure could contribute to DEATH or SERIOUS INJURY.',
            'Every person working on this software MUST follow these procedures.',
            'A government audit will verify compliance for EVERY change.',
        ],
        accent_color=RED, bg_color=RED_BG, icon_char='!'
    ))
    s.append(Spacer(1, 6))

    s.append(CalloutBox(
        'The Auditor Will...',
        [
            'Pick random Git commits and trace them to requirements, risk analysis, and tests',
            'Pick random requirements and trace them to code and verification evidence',
            'Ask to see signed review records, test results, and problem reports',
            'Check that templates (PDFs in docs/iec62304/templates/) are being used',
        ],
        accent_color=NAVY, bg_color=LIGHT_BG, icon_char='?'
    ))
    s.append(Spacer(1, 8))

    # ─── Table of Contents ───
    s.append(Paragraph('<b>Contents</b>', ST['section']))
    toc_items = [
        '1. For Developers — Daily Workflow',
        '2. For QA / Testers — Testing Workflow',
        '3. For Project Lead — Management Workflow',
        '4. For Clinical Advisor — Clinical Workflow',
        '5. Record Keeping — Where to Store Everything',
        '6. Quick Reference — What Template to Use When',
        '7. Audit Preparation Checklist',
        '8. Common Mistakes to Avoid',
        '9. Contact and Escalation',
    ]
    for item in toc_items:
        s.append(Paragraph(item, ST['toc_entry']))
    s.append(Spacer(1, 6))

    # ═══════════════════════════════════════
    # SECTION 1: DEVELOPERS
    # ═══════════════════════════════════════
    s.append(PageBreak())
    s.append(SectionBadge('1', 'FOR DEVELOPERS — Daily Workflow', TEAL))
    s.append(Spacer(1, 8))

    # Step 1
    s.append(StepNumber('1', 'Before Starting Any Work'))
    s.append(Spacer(1, 3))
    s.append(CheckItem('Check GitHub Issues for assigned task'))
    s.append(CheckItem('Identify which requirement(s) the task implements'))
    s.append(Paragraph(
        '    → Open <font face="Courier" size="7">docs/iec62304/02_Software_Requirements_Specification.md</font>',
        ST['body_indent']))
    s.append(Paragraph('    → Find the REQ-ID (e.g., REQ-FUNC-040)', ST['body_indent']))
    s.append(Paragraph('    → <b>If no requirement exists, STOP and create one first</b>', ST['body_indent']))
    s.append(CheckItem('Check if the task touches a Class C module'))
    s.append(Paragraph('    → If YES: read the risk analysis in RMF-001', ST['body_indent']))
    s.append(Paragraph('    → If YES: your PR will need extra scrutiny (2 reviewers)', ST['body_indent']))
    s.append(CheckItem('Create a feature branch from main'))
    s.append(CodeBlock(['git checkout -b feature/REQ-FUNC-040-description']))
    s.append(Spacer(1, 6))

    # Step 2
    s.append(StepNumber('2', 'While Writing Code'))
    s.append(Spacer(1, 3))
    s.append(Paragraph('<b>Follow coding standards:</b>', ST['body']))
    s.append(Paragraph('    → TypeScript: ESLint rules + TypeScript strict mode', ST['body_indent']))
    s.append(Paragraph('    → Python: PEP 8 + type annotations', ST['body_indent']))
    s.append(Spacer(1, 3))
    s.append(Paragraph('<b>For Class C modules:</b>', ST['body']))
    s.append(CheckItem('Add input validation for ALL external inputs', indent=12))
    s.append(CheckItem('Handle ALL error cases (no silent failures)', indent=12))
    s.append(CheckItem('Add unit tests for the change', indent=12))
    s.append(CheckItem('Document safety-related behavior in code comments', indent=12))
    s.append(Spacer(1, 3))
    s.append(Paragraph('<b>Commit message format:</b>', ST['body']))
    s.append(CodeBlock([
        'git commit -m "feat(REQ-FUNC-040): Implement volume computation',
        '',
        '  Implements voxel counting with normative percentile comparison.',
        '  Risk control RC-004 (volumetry displays percentile ranges).',
        '  Unit test: UT-VOL-001"',
    ]))
    s.append(Spacer(1, 6))

    # Step 3
    s.append(StepNumber('3', 'Submitting a Pull Request'))
    s.append(Spacer(1, 3))
    s.append(Paragraph('<b>PR Title:</b> [REQ-ID] Brief description', ST['body']))
    s.append(Paragraph('Example: <font face="Courier" size="7.5">[REQ-FUNC-040] Brain volumetry computation</font>', ST['body_indent']))
    s.append(Spacer(1, 3))
    s.append(Paragraph('<b>PR Description MUST include:</b>', ST['body']))
    s.append(CheckItem('What: description of the change'))
    s.append(CheckItem('Why: which requirement it implements'))
    s.append(CheckItem('Risk: which hazards are affected (if any)'))
    s.append(CheckItem('Tests: which tests verify the change'))
    s.append(CheckItem('SOUP: any new dependencies added?'))
    s.append(Spacer(1, 3))
    s.append(CalloutBox(
        'CI Pipeline — ALL must be GREEN before requesting review',
        [
            'TypeScript check (npx tsc --noEmit)',
            'Frontend build (npm run build)',
            'Backend tests (python -m pytest)',
            'SOUP vulnerability scan (npm audit + pip-audit)',
            'Python syntax check (ast.parse all .py files)',
        ],
        accent_color=GREEN, bg_color=GREEN_BG, icon_char='✓'
    ))
    s.append(Spacer(1, 3))
    s.append(CheckItem('Request review from at least 1 team member'))
    s.append(CheckItem('For Class C changes: request review from 2 team members'))
    s.append(Spacer(1, 6))

    # Step 4
    s.append(StepNumber('4', 'Code Review (as Reviewer)'))
    s.append(Spacer(1, 3))
    s.append(CalloutBox(
        'Use Template: TPL-03 Code Review Checklist',
        ['Location: docs/iec62304/templates/TPL-03_Code_Review_Checklist.pdf',
         'This filled form is AUDIT EVIDENCE — it must be saved!'],
        accent_color=PURPLE, bg_color=PURPLE_BG, icon_char='T'
    ))
    s.append(Spacer(1, 4))
    s.append(Paragraph('<b>General Checks:</b>', ST['body']))
    s.append(CheckItem('Code implements the detailed design (DD-001)'))
    s.append(CheckItem('Coding standards followed'))
    s.append(CheckItem('No commented-out code without issue link'))
    s.append(Spacer(1, 3))
    s.append(Paragraph('<b>Safety Checks (Class B/C):</b>', ST['body']))
    s.append(CheckItem('Input validation for all external inputs'))
    s.append(CheckItem('Error handling covers all failure modes'))
    s.append(CheckItem('No unhandled exceptions'))
    s.append(CheckItem('Risk controls correctly implemented'))
    s.append(Spacer(1, 3))
    s.append(Paragraph('<b>Class C Specific:</b>', ST['body']))
    s.append(CheckItem('No unintended functionality'))
    s.append(CheckItem('Robustness with invalid inputs'))
    s.append(CheckItem('SOUP APIs used correctly'))
    s.append(Spacer(1, 4))
    s.append(Paragraph('<b>Save the filled checklist:</b>', ST['body']))
    s.append(CodeBlock([
        'Filename: CR-YYYY-NNN_[module_name].pdf',
        'Store in: docs/iec62304/records/code_reviews/',
    ]))
    s.append(Spacer(1, 6))

    # Step 5
    s.append(StepNumber('5', 'After Merge and Deploy'))
    s.append(Spacer(1, 3))
    s.append(Paragraph('<b>For backend changes:</b>', ST['body']))
    s.append(CodeBlock([
        'gcloud builds submit --config=cloudbuild.yaml \\',
        '  --substitutions=COMMIT_SHA=$(git rev-parse --short HEAD)',
        '',
        '# Wait for build SUCCESS, then:',
        'bash test_endpoints.sh    # ALL 9 checks must PASS',
    ]))
    s.append(Spacer(1, 3))
    s.append(Paragraph('<b>For frontend changes:</b>', ST['body']))
    s.append(CodeBlock([
        'cd frontend && npm run build',
        'npx firebase deploy --only hosting',
        '# Verify the app loads correctly in browser',
    ]))
    s.append(Spacer(1, 8))

    # ═══════════════════════════════════════
    # SECTION 2: QA / TESTERS
    # ═══════════════════════════════════════
    s.append(PageBreak())
    s.append(SectionBadge('2', 'FOR QA / TESTERS — Testing Workflow', BLUE))
    s.append(Spacer(1, 8))

    s.append(Paragraph('<b>Testing a Requirement</b>', ST['subsection']))
    s.append(Spacer(1, 3))
    s.append(CalloutBox(
        'Use Template: TPL-06 Test Execution Report',
        ['Location: docs/iec62304/templates/TPL-06_Test_Execution_Report.pdf'],
        accent_color=BLUE, bg_color=BLUE_BG, icon_char='T'
    ))
    s.append(Spacer(1, 4))
    s.append(CheckItem('Find the requirement in SRS-001'))
    s.append(CheckItem('Fill in ALL fields: Test ID, Requirement, Software Version, Environment, Tester, Date'))
    s.append(CheckItem('Write clear test steps (preconditions, step-by-step, expected result)'))
    s.append(CheckItem('Execute test and document actual result + PASS/FAIL'))
    s.append(CheckItem('Save: ST-FUNC-XXX_[date].pdf in docs/iec62304/records/test_results/'))
    s.append(Spacer(1, 8))

    s.append(Paragraph('<b>Testing a Risk Control</b>', ST['subsection']))
    s.append(Spacer(1, 3))
    s.append(CalloutBox(
        'Use Template: TPL-04 Risk Control Verification',
        ['Location: docs/iec62304/templates/TPL-04_Risk_Control_Verification.pdf',
         'There are 22 risk controls (RC-001 through RC-022) — ALL must be verified.'],
        accent_color=AMBER, bg_color=AMBER_BG, icon_char='T'
    ))
    s.append(Spacer(1, 4))
    s.append(CheckItem('Find risk control in RMF-001 (docs/iec62304/03_Risk_Management_File.md, Section 5)'))
    s.append(CheckItem('Verify the control is implemented in the code'))
    s.append(CheckItem('Test that it works correctly'))
    s.append(CheckItem('Document verification method and result'))
    s.append(CheckItem('Sign and date'))
    s.append(CheckItem('Save: RCV-RC-XXX_[date].pdf in docs/iec62304/records/risk_verification/'))
    s.append(Spacer(1, 8))

    # ═══════════════════════════════════════
    # SECTION 3: PROJECT LEAD
    # ═══════════════════════════════════════
    s.append(PageBreak())
    s.append(SectionBadge('3', 'FOR PROJECT LEAD — Management Workflow', PURPLE))
    s.append(Spacer(1, 8))

    s.append(Paragraph('<b>Release Process</b>', ST['subsection']))
    s.append(CheckItem('Fill the Pre-Release Checklist (TPL-02_Release_Checklist.pdf)'))
    s.append(CheckItem('All 11 checks must be marked YES'))
    s.append(CheckItem('Document any known anomalies with risk assessment'))
    s.append(CheckItem('Sign the approval section'))
    s.append(Spacer(1, 3))
    s.append(Paragraph('<b>Quality Gates:</b> Use TPL-10 for each gate:', ST['body']))
    s.append(Paragraph('G1 (Requirements) → G2 (Design) → G3 (Implementation) → G4 (Integration) → G5 (Release)', ST['body_indent']))
    s.append(Spacer(1, 8))

    s.append(Paragraph('<b>Monthly Tasks</b>', ST['subsection']))
    s.append(CalloutBox(
        'SOUP Vulnerability Review — MONTHLY (Mandatory)',
        [
            'Use TPL-07_SOUP_Vulnerability_Review.pdf',
            'Run: npm audit (frontend) + pip-audit (backend)',
            'Check NVD for 7 Class C SOUP items',
            'Document findings and actions, sign and date',
            'Store in: docs/iec62304/records/soup_reviews/',
        ],
        accent_color=RED, bg_color=RED_BG, icon_char='M'
    ))
    s.append(Spacer(1, 4))
    s.append(CalloutBox(
        'Risk Management File Review — QUARTERLY',
        [
            'Review RMF-001 for new hazards',
            'Check if any changes introduced new risks',
            'Update if needed, document review in RMF-001 Section 7',
        ],
        accent_color=AMBER, bg_color=AMBER_BG, icon_char='Q'
    ))
    s.append(Spacer(1, 8))

    s.append(Paragraph('<b>When a Bug is Found</b>', ST['subsection']))
    s.append(CheckItem('Create GitHub Issue using problem report format'))
    s.append(CheckItem('Use TPL-01_Problem_Report.pdf for formal documentation'))
    s.append(Spacer(1, 3))
    s.append(CalloutBox(
        'CRITICAL: Always Assess Safety Impact',
        [
            'Does this affect a Class C module?',
            'Could this contribute to a hazardous situation?',
            'Does this require regulatory notification (EU MDR Article 87)?',
            'If safety-impacted: Use TPL-08, notify authority within 24 hours if serious',
        ],
        accent_color=RED, bg_color=RED_BG, icon_char='!'
    ))
    s.append(Spacer(1, 6))

    s.append(Paragraph('<b>Document Approval</b>', ST['subsection']))
    s.append(Paragraph('Use <b>TPL-11_Document_Approval.pdf</b> — all 15 IEC 62304 documents need formal approval signatures.', ST['body']))
    s.append(Paragraph('Each document needs: Reviewer name + Approver name + Date + Signature.', ST['body']))
    s.append(Paragraph('Store signed original in: <font face="Courier" size="7">docs/iec62304/records/approvals/</font>', ST['body']))
    s.append(Spacer(1, 8))

    # ═══════════════════════════════════════
    # SECTION 4: CLINICAL ADVISOR
    # ═══════════════════════════════════════
    s.append(SectionBadge('4', 'FOR CLINICAL ADVISOR — Clinical Workflow', GREEN))
    s.append(Spacer(1, 8))

    s.append(Paragraph('<b>Risk Analysis Review</b>', ST['subsection']))
    s.append(CheckItem('Review RMF-001: Are all 14 hazardous situations clinically accurate?'))
    s.append(CheckItem('Are severity ratings appropriate?'))
    s.append(CheckItem('Are risk control measures clinically adequate?'))
    s.append(CheckItem('Is the benefit-risk analysis justified?'))
    s.append(CheckItem('Sign off using TPL-05_Design_Review_Record.pdf'))
    s.append(Spacer(1, 6))

    s.append(Paragraph('<b>Requirements Review</b>', ST['subsection']))
    s.append(CheckItem('Review safety requirements (REQ-SAFE-001 through REQ-SAFE-020)'))
    s.append(CheckItem('Are disclaimers clinically appropriate?'))
    s.append(CheckItem('Is the "assistive tool" positioning clear?'))
    s.append(CheckItem('Are confidence thresholds clinically meaningful?'))
    s.append(CheckItem('Are AI performance thresholds appropriate?'))
    s.append(CheckItem('Is the de-identification approach adequate for HIPAA?'))
    s.append(Spacer(1, 8))

    # ═══════════════════════════════════════
    # SECTION 5: RECORD KEEPING
    # ═══════════════════════════════════════
    s.append(PageBreak())
    s.append(SectionBadge('5', 'Record Keeping — Where to Store Everything', NAVY_LIGHT))
    s.append(Spacer(1, 8))

    s.append(Paragraph('<b>Folder Structure</b>', ST['subsection']))
    s.append(CodeBlock([
        'docs/iec62304/records/',
        '├── code_reviews/           ← Filled TPL-03 for each PR',
        '│   ├── CR-2026-001_volumetry_service.pdf',
        '│   └── ...',
        '├── test_results/           ← Filled TPL-06 for each test',
        '│   ├── ST-FUNC-001_load_nifti.pdf',
        '│   └── ...',
        '├── risk_verification/      ← Filled TPL-04 for each risk control',
        '│   ├── RCV-RC-001_ai_disclaimer.pdf',
        '│   └── ...',
        '├── soup_reviews/           ← Filled TPL-07 monthly',
        '│   ├── SOUP-2026-04.pdf',
        '│   └── ...',
        '├── releases/               ← Filled TPL-02 per release',
        '├── design_reviews/         ← Filled TPL-05 per review',
        '├── incidents/              ← Filled TPL-08 if needed',
        '├── changes/                ← Filled TPL-09 per change',
        '├── gate_approvals/         ← Filled TPL-10 per gate',
        '└── approvals/              ← Filled TPL-11 document sign-off',
    ]))
    s.append(Spacer(1, 6))

    s.append(Paragraph('<b>Naming Convention</b>', ST['subsection']))
    s.append(Paragraph('[Template Type]-[ID]_[Description]_[Date].pdf', ST['code']))
    s.append(Spacer(1, 3))
    s.append(table(
        ['Example Filename', 'Description'],
        [
            ['CR-2026-001_brain_volumetry_service_2026-04-15.pdf', 'Code review record'],
            ['ST-FUNC-040_compute_volumes_2026-04-16.pdf', 'Test execution report'],
            ['RCV-RC-004_volumetry_percentile_display_2026-04-17.pdf', 'Risk control verification'],
            ['SOUP-2026-04_monthly_review.pdf', 'Monthly SOUP vulnerability review'],
            ['REL-v2.0.0_release_checklist_2026-04-20.pdf', 'Release checklist'],
        ],
        col_widths=[90 * mm, 72 * mm]
    ))
    s.append(Spacer(1, 8))

    # ═══════════════════════════════════════
    # SECTION 6: QUICK REFERENCE
    # ═══════════════════════════════════════
    s.append(SectionBadge('6', 'Quick Reference — What Template to Use When', TEAL))
    s.append(Spacer(1, 8))
    s.append(table_colored_first_col(
        ['Situation', 'Template', 'File'],
        [
            ["I'm reviewing someone's code", 'Code Review Checklist', 'TPL-03'],
            ["I'm deploying a new version", 'Release Checklist', 'TPL-02'],
            ['I found a bug', 'Problem Report', 'TPL-01'],
            ["I'm testing a requirement", 'Test Execution Report', 'TPL-06'],
            ["I'm verifying a risk control", 'Risk Control Verification', 'TPL-04'],
            ["I'm reviewing architecture/design", 'Design Review Record', 'TPL-05'],
            ['Monthly SOUP vulnerability check', 'SOUP Vulnerability Review', 'TPL-07'],
            ['A serious safety incident occurred', 'Serious Incident Report', 'TPL-08'],
            ['Making a significant code change', 'Change Control Record', 'TPL-09'],
            ['Approving a development phase gate', 'Quality Gate Approval', 'TPL-10'],
            ['Formally approving all documents', 'Document Approval Record', 'TPL-11'],
        ],
        col_widths=[58 * mm, 44 * mm, 60 * mm]
    ))
    s.append(Spacer(1, 8))

    # ═══════════════════════════════════════
    # SECTION 7: AUDIT PREPARATION
    # ═══════════════════════════════════════
    s.append(PageBreak())
    s.append(SectionBadge('7', 'Audit Preparation Checklist', RED))
    s.append(Spacer(1, 6))
    s.append(CalloutBox(
        'When the audit is announced, verify ALL of the following:',
        [],
        accent_color=RED, bg_color=RED_BG, icon_char='!'
    ))
    s.append(Spacer(1, 4))
    audit_checks = [
        'All 15 IEC 62304 documents exist and are current version',
        'All 11 PDF templates have been used (filled records exist)',
        'Document Approval Record (TPL-11) is signed by authority',
        'At least 1 filled Code Review Checklist per Class C module change',
        'At least 1 filled Test Execution Report per "Must" requirement',
        'All 22 Risk Control Verification records filled and signed',
        'Monthly SOUP Vulnerability Reviews exist for the past 6 months',
        'Release Checklists exist for each deployed version',
        'Git history shows PR reviews on all changes to main branch',
        'CI pipeline results are available (GitHub Actions artifacts)',
        'test_endpoints.sh results available for pre/post deploy',
        'No critical/major open bugs without safety assessment',
    ]
    for chk in audit_checks:
        s.append(CheckItem(chk))
    s.append(Spacer(1, 8))

    # ═══════════════════════════════════════
    # SECTION 8: COMMON MISTAKES
    # ═══════════════════════════════════════
    s.append(SectionBadge('8', 'Common Mistakes to Avoid', AMBER))
    s.append(Spacer(1, 8))
    s.append(table(
        ['Mistake', 'Why It\'s a Problem', 'What To Do Instead'],
        [
            ['Pushing directly to main', 'No review evidence = audit failure', 'Always use pull requests'],
            ['"Fix typo" commit without PR', 'Uncontrolled change = finding', 'Every change needs a PR'],
            ['No commit message references', "Auditor can't trace changes", 'Include REQ-ID or issue #'],
            ['Skipping test_endpoints.sh', "Can't prove deploy verified", 'Run BEFORE and AFTER deploy'],
            ['Not filling PDF templates', 'No audit evidence exists', 'Fill templates, save as records'],
            ['Ignoring SOUP vulnerabilities', 'Cybersecurity non-compliance', 'Monthly review is MANDATORY'],
            ['Changing Class C without review', 'IEC 62304 5.5.4 violation', 'ALWAYS get code review'],
            ['Not assessing safety of bugs', 'ISO 14971 violation', 'Every bug must assess safety'],
        ],
        col_widths=[42 * mm, 50 * mm, 70 * mm]
    ))
    s.append(Spacer(1, 8))

    # ═══════════════════════════════════════
    # SECTION 9: CONTACT & ESCALATION
    # ═══════════════════════════════════════
    s.append(SectionBadge('9', 'Contact and Escalation', MED_GRAY))
    s.append(Spacer(1, 8))
    s.append(table(
        ['Issue', 'Contact', 'Escalation'],
        [
            ['Code review question', 'Assigned reviewer', 'Project Lead'],
            ['Safety concern about a change', 'Project Lead', 'Clinical Advisor'],
            ['Serious incident suspected', 'Project Lead + Clinical Advisor', 'Regulatory Authority (BfArM) within 24h'],
            ['SOUP vulnerability (critical)', 'Developer', 'Project Lead for risk assessment'],
            ['Audit preparation question', 'Project Lead', 'Regulatory Affairs'],
        ],
        col_widths=[45 * mm, 55 * mm, 62 * mm]
    ))
    s.append(Spacer(1, 10))

    # ─── References ───
    s.append(Paragraph('<b>References</b>', ST['subsection']))
    s.append(Paragraph('All IEC 62304 documentation: <font face="Courier" size="7">docs/iec62304/</font>', ST['body']))
    s.append(Paragraph('All fillable templates: <font face="Courier" size="7">docs/iec62304/templates/</font>', ST['body']))
    s.append(Paragraph('All filled records: <font face="Courier" size="7">docs/iec62304/records/</font>', ST['body']))
    s.append(Spacer(1, 6))
    s.append(table(
        ['Document', 'ID', 'Purpose'],
        [
            ['Master Compliance Document', '00', 'Overall compliance status'],
            ['Software Requirements Spec', 'SRS-001', 'All 91 requirements'],
            ['Risk Management File', 'RMF-001', '14 hazards, 22 risk controls'],
            ['Detailed Design Specification', 'DD-001', 'Class C unit designs'],
            ['Traceability Matrix', 'TM-001', 'Requirement ↔ test mapping'],
        ],
        col_widths=[52 * mm, 24 * mm, 86 * mm]
    ))

    # ─── Footer ───
    s.append(Spacer(1, 14))
    s.append(GradientBar(height=4))
    s.append(Spacer(1, 6))
    s.append(Paragraph(
        '<i>This guide must be read by every team member before contributing to MSTool-AI. '
        'Acknowledgment of reading this guide should be documented.</i>',
        ST['body']))
    s.append(Spacer(1, 4))
    s.append(Paragraph(
        f'MSTool-AI Team Operating Guide  |  GUIDE-001 v1.0  |  Generated {NOW}  |  CONFIDENTIAL',
        ST['small']))

    doc.build(s,
              onFirstPage=lambda c, d: hf_guide(c, d, 'Team Operating Guide — IEC 62304 Compliance', 'GUIDE-001'),
              onLaterPages=lambda c, d: hf_guide(c, d, 'Team Operating Guide — IEC 62304 Compliance', 'GUIDE-001'))
    print(f'  OK MSTool-AI_Team_Guide_IEC62304.pdf')


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

if __name__ == '__main__':
    print('\n  MSTool-AI - Generating Premium PDF Documents')
    print('  ' + '=' * 50)
    generate_claude_md_pdf()
    generate_team_guide_pdf()
    print('  ' + '=' * 50)
    print(f'  Output: {OUTPUT_DIR}')
    print('  Done.\n')
