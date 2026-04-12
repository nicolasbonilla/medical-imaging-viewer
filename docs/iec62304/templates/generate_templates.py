"""
Generate IEC 62304 Class C fillable PDF templates — Premium Design.

Professional audit-ready PDF forms with:
- Clean field boxes with light gray background for writing areas
- Professional navy/teal color scheme
- MSTool-AI branding
- Proper spacing for handwritten or typed entries
- No obstructing lines in fill areas
"""

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.colors import HexColor, white
from reportlab.lib.units import mm
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, Flowable,
)
import os
from datetime import datetime

# ─── Colors ───
NAVY = HexColor('#0F172A')
TEAL = HexColor('#0D9488')
BLUE = HexColor('#2563EB')
LIGHT_BG = HexColor('#F8FAFC')
FILL_BG = HexColor('#F1F5F9')
MED_GRAY = HexColor('#94A3B8')
DARK_GRAY = HexColor('#334155')
BORDER = HexColor('#E2E8F0')
TABLE_HEADER = HexColor('#1E3A5F')
TABLE_ALT = HexColor('#F8FAFC')
ACCENT = HexColor('#0EA5E9')

PAGE_W, PAGE_H = A4
MARGIN = 18 * mm
CONTENT_W = PAGE_W - 2 * MARGIN
OUTPUT_DIR = os.path.dirname(__file__)

def S(name, **kw):
    d = dict(fontName='Helvetica', fontSize=9, textColor=DARK_GRAY, leading=12)
    d.update(kw)
    return ParagraphStyle(name, **d)

ST = {
    'title': S('t', fontName='Helvetica-Bold', fontSize=15, textColor=NAVY, alignment=TA_CENTER, spaceAfter=2),
    'subtitle': S('st', fontSize=9, textColor=MED_GRAY, alignment=TA_CENTER, spaceAfter=10),
    'section': S('sec', fontName='Helvetica-Bold', fontSize=10, textColor=NAVY, spaceBefore=12, spaceAfter=5),
    'subsection': S('ss', fontName='Helvetica-Bold', fontSize=9, textColor=TEAL, spaceBefore=8, spaceAfter=3),
    'body': S('b', fontSize=8.5, textColor=DARK_GRAY, spaceAfter=3, leading=11),
    'small': S('sm', fontSize=7, textColor=MED_GRAY, leading=9),
    'th': S('th', fontName='Helvetica-Bold', fontSize=7.5, textColor=white, leading=10),
    'td': S('td', fontSize=8, textColor=DARK_GRAY, leading=10),
    'label': S('lb', fontName='Helvetica-Bold', fontSize=8, textColor=HexColor('#475569')),
    'check': S('ck', fontSize=8.5, textColor=DARK_GRAY, leading=13),
}


class FieldBox(Flowable):
    """A labeled field with gray fill area for writing."""
    def __init__(self, label, width, height=18, value=''):
        Flowable.__init__(self)
        self.label_text = label
        self.box_width = width
        self.box_height = height
        self.value = value
        self.width = width
        self.height = height + 14

    def draw(self):
        # Label
        self.canv.setFillColor(HexColor('#475569'))
        self.canv.setFont('Helvetica-Bold', 7.5)
        self.canv.drawString(0, self.box_height + 3, self.label_text)
        # Box
        self.canv.setFillColor(FILL_BG)
        self.canv.setStrokeColor(BORDER)
        self.canv.setLineWidth(0.5)
        self.canv.roundRect(0, 0, self.box_width, self.box_height, 3, fill=1, stroke=1)
        # Value if provided
        if self.value:
            self.canv.setFillColor(DARK_GRAY)
            self.canv.setFont('Helvetica', 8.5)
            self.canv.drawString(6, self.box_height - 12, self.value)


class CheckItem(Flowable):
    """A checkbox item with text."""
    def __init__(self, text, width):
        Flowable.__init__(self)
        self.text = text
        self.item_width = width
        self.width = width
        self.height = 16

    def draw(self):
        # Checkbox
        self.canv.setStrokeColor(BORDER)
        self.canv.setFillColor(white)
        self.canv.setLineWidth(0.6)
        self.canv.roundRect(0, 3, 10, 10, 1.5, fill=1, stroke=1)
        # Text
        self.canv.setFillColor(DARK_GRAY)
        self.canv.setFont('Helvetica', 8)
        self.canv.drawString(15, 4, self.text[:100])


def hf(canvas, doc, title, doc_id):
    """Header and footer."""
    canvas.saveState()
    # Header bar
    canvas.setFillColor(NAVY)
    canvas.rect(0, PAGE_H - 12 * mm, PAGE_W, 12 * mm, fill=1, stroke=0)
    canvas.setFillColor(TEAL)
    canvas.rect(0, PAGE_H - 12.5 * mm, PAGE_W, 0.5 * mm, fill=1, stroke=0)
    # Header text
    canvas.setFillColor(white)
    canvas.setFont('Helvetica-Bold', 9)
    canvas.drawString(MARGIN, PAGE_H - 9 * mm, 'MSTool-AI')
    canvas.setFont('Helvetica', 7)
    canvas.drawRightString(PAGE_W - MARGIN, PAGE_H - 9 * mm, f'{doc_id}  |  {title}')
    # Footer
    canvas.setFillColor(MED_GRAY)
    canvas.setFont('Helvetica', 6)
    canvas.drawString(MARGIN, 8 * mm, 'IEC 62304:2006+A1:2015 Class C  |  IEC 81001-5-1:2021  |  ISO 14971:2019  |  CONFIDENTIAL')
    canvas.drawRightString(PAGE_W - MARGIN, 8 * mm, f'Page {doc.page}')
    canvas.setStrokeColor(BORDER)
    canvas.setLineWidth(0.3)
    canvas.line(MARGIN, 11 * mm, PAGE_W - MARGIN, 11 * mm)
    canvas.restoreState()


def field(label, width=None, height=18, value=''):
    return FieldBox(label, width or CONTENT_W, height, value)


def field_pair(l1, l2, ratio=0.5):
    """Two fields side by side."""
    w1 = CONTENT_W * ratio - 3
    w2 = CONTENT_W * (1 - ratio) - 3
    t = Table([[FieldBox(l1, w1), FieldBox(l2, w2)]], colWidths=[w1 + 6, w2 + 6])
    t.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (0,0), (-1,-1), 0), ('RIGHTPADDING', (0,0), (-1,-1), 0)]))
    return t


def check(text):
    return CheckItem(text, CONTENT_W)


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


def build(filename, title, doc_id, parent, content_fn):
    path = os.path.join(OUTPUT_DIR, filename)
    doc = SimpleDocTemplate(path, pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN,
                            topMargin=18 * mm, bottomMargin=16 * mm, title=title)
    s = []
    s.append(Spacer(1, 6))
    s.append(Paragraph(title, ST['title']))
    s.append(Paragraph(f'{doc_id}  |  Parent Document: {parent}', ST['subtitle']))
    s.append(HRFlowable(width=CONTENT_W, thickness=1, color=TEAL))
    s.append(Spacer(1, 6))

    # Doc control
    s.append(Paragraph('DOCUMENT CONTROL', ST['section']))
    s.append(field_pair('Document ID', 'Version'))
    s.append(field_pair('Date', 'Project'))
    s.append(field_pair('Prepared By', 'Reviewed By'))
    s.append(field('Approved By'))
    s.append(Spacer(1, 6))

    content_fn(s)

    # Footer
    s.append(Spacer(1, 10))
    s.append(HRFlowable(width=CONTENT_W, thickness=0.3, color=BORDER))
    s.append(Paragraph(
        f'MSTool-AI IEC 62304 Class C Regulatory Documentation  |  Generated {datetime.now().strftime("%Y-%m-%d")}',
        ST['small']))

    doc.build(s, onFirstPage=lambda c, d: hf(c, d, title, doc_id),
              onLaterPages=lambda c, d: hf(c, d, title, doc_id))
    print(f'  {filename}')


# ═══════════════════════════════════════════════════════════════
# TEMPLATES
# ═══════════════════════════════════════════════════════════════

def t01_problem_report(s):
    s.append(Paragraph('PROBLEM DESCRIPTION', ST['section']))
    s.append(field_pair('Problem ID', 'Severity: Critical / Major / Minor'))
    s.append(field_pair('Reporter', 'Date Reported'))
    s.append(field('Software Version / Git SHA'))
    s.append(field('Description', height=40))
    s.append(field('Steps to Reproduce', height=40))
    s.append(field_pair('Expected Behavior', 'Actual Behavior'))

    s.append(Paragraph('SAFETY IMPACT ASSESSMENT', ST['section']))
    s.append(check('Could contribute to a hazardous situation (HAZ-ID: __________)'))
    s.append(check('Affects a Class C software item (specify: __________________)'))
    s.append(check('Requires regulatory notification (EU MDR Article 87)'))
    s.append(field('Safety Impact Details', height=30))

    s.append(Paragraph('INVESTIGATION & RESOLUTION', ST['section']))
    s.append(field('Root Cause Analysis', height=40))
    s.append(field('Affected Software Items'))
    s.append(field('Corrective Action / Fix Description', height=30))
    s.append(field_pair('Fix Commit SHA', 'Fix Version'))
    s.append(field_pair('Regression Test Result: PASS / FAIL', 'Verified By'))
    s.append(Paragraph('CLOSURE', ST['subsection']))
    s.append(field_pair('Closed By', 'Close Date'))
    s.append(field('Closure Signature'))


def t02_release_checklist(s):
    s.append(Paragraph('RELEASE INFORMATION', ST['section']))
    s.append(field_pair('Release Version', 'Release Date'))
    s.append(field('Release Manager'))

    s.append(Paragraph('PRE-RELEASE VERIFICATION (IEC 62304 Clause 5.8.1)', ST['section']))
    items = [
        'All unit tests pass (Class C units) — CI pipeline green',
        'Integration tests pass (test_endpoints.sh 9/9 PASS)',
        'TypeScript compilation successful (npx tsc --noEmit)',
        'Python syntax check passes (all .py files)',
        'Code review completed for all changes since last release',
        'No critical/major open bugs (GitHub Issues reviewed)',
        'Risk analysis updated if applicable (RMF-001)',
        'SOUP list updated if dependencies changed (SOUP-001)',
        'Traceability matrix updated (TM-001)',
        'SOUP vulnerability scan clean (npm audit + pip-audit)',
        'Known anomalies documented (section below)',
    ]
    for item in items:
        s.append(check(item))

    s.append(Paragraph('KNOWN RESIDUAL ANOMALIES (IEC 62304 Clause 5.8.2)', ST['section']))
    s.append(table(
        ['ID', 'Description', 'Severity', 'Safety Impact', 'Disposition'],
        [['', '', '', '', ''], ['', '', '', '', ''], ['', '', '', '', ''], ['', '', '', '', '']],
        col_widths=[18*mm, 55*mm, 18*mm, 25*mm, 46*mm]
    ))

    s.append(Paragraph('DEPLOYMENT RECORD', ST['section']))
    s.append(field_pair('Backend Cloud Build ID', 'Backend Deploy Time'))
    s.append(field_pair('Frontend Firebase Version', 'Frontend Deploy Time'))
    s.append(field('Post-Deploy Verification: test_endpoints.sh'))
    s.append(check('All 9/9 endpoint checks PASS'))
    s.append(check('Manual smoke test completed'))

    s.append(Paragraph('RELEASE APPROVAL', ST['section']))
    s.append(field_pair('Approved By', 'Approval Date'))
    s.append(field('Signature'))


def t03_code_review(s):
    s.append(Paragraph('REVIEW CONTEXT', ST['section']))
    s.append(field_pair('Review ID', 'Pull Request #'))
    s.append(field_pair('Module / Software Unit', 'Safety Class: A / B / C'))
    s.append(field_pair('Author', 'Reviewer'))
    s.append(field('Date'))

    s.append(Paragraph('CODE REVIEW CHECKLIST (IEC 62304 Clause 5.5.3, 5.5.4)', ST['section']))
    s.append(Paragraph('General', ST['subsection']))
    s.append(check('Code implements the detailed design specification (DD-001)'))
    s.append(check('Coding standards followed (ESLint for TypeScript / PEP 8 for Python)'))
    s.append(check('No commented-out code without linked issue'))
    s.append(check('Code comments appropriate and up to date'))

    s.append(Paragraph('Safety (Class B and C)', ST['subsection']))
    s.append(check('Input validation present for all external inputs'))
    s.append(check('Error handling covers all failure modes from detailed design'))
    s.append(check('No unhandled exceptions / promise rejections'))
    s.append(check('Safety-critical calculations verified (units, ranges, overflow)'))
    s.append(check('Risk control measures correctly implemented (HAZ-IDs: _______)'))

    s.append(Paragraph('Security (IEC 81001-5-1)', ST['subsection']))
    s.append(check('No hardcoded credentials or secrets'))
    s.append(check('Input sanitization against injection'))
    s.append(check('Authentication/authorization checked on endpoints'))

    s.append(Paragraph('Class C Specific (IEC 62304 Clause 5.5.4)', ST['subsection']))
    s.append(check('No unintended functionality'))
    s.append(check('Robustness with invalid inputs verified'))
    s.append(check('SOUP APIs used correctly per documentation'))
    s.append(check('Memory management adequate'))

    s.append(Paragraph('RESULT', ST['section']))
    s.append(check('APPROVED'))
    s.append(check('APPROVED WITH COMMENTS'))
    s.append(check('REJECTED'))
    s.append(field('Comments', height=40))
    s.append(field_pair('Reviewer Signature', 'Date'))
    s.append(field('Author Acknowledgment Signature'))


def t04_risk_control(s):
    s.append(Paragraph('RISK CONTROL IDENTIFICATION', ST['section']))
    s.append(field_pair('Risk Control ID: RC-____', 'Hazard Reference: HAZ-____'))
    s.append(field('Requirement Reference: REQ-SAFE-____'))
    s.append(field('Risk Control Description', height=30))
    s.append(field('Implementation Location (file path, function, line)', height=20))

    s.append(Paragraph('VERIFICATION METHOD', ST['section']))
    s.append(check('Automated Test'))
    s.append(check('Manual Test'))
    s.append(check('Code Inspection'))
    s.append(check('Analysis / Demonstration'))
    s.append(field('Test ID (if applicable)'))
    s.append(field('Test Procedure / Inspection Method', height=40))
    s.append(field('Expected Result', height=25))
    s.append(field('Actual Result', height=25))

    s.append(Paragraph('CONCLUSION', ST['section']))
    s.append(check('PASS — Risk control is effective'))
    s.append(check('FAIL — Risk control is NOT effective (escalate to Risk Management Authority)'))
    s.append(field('Additional Notes', height=25))
    s.append(field_pair('Verified By', 'Verification Date'))
    s.append(field('Signature'))


def t05_design_review(s):
    s.append(Paragraph('REVIEW SCOPE', ST['section']))
    s.append(check('Architecture Review (IEC 62304 Clause 5.3.6)'))
    s.append(check('Detailed Design Review — Class C (IEC 62304 Clause 5.4.4)'))
    s.append(field('Document(s) Reviewed (e.g., DD-AI-001, SAD Section 2)'))
    s.append(field_pair('Review Date', 'Reviewer(s)'))

    s.append(Paragraph('REVIEW CHECKLIST', ST['section']))
    s.append(check('Design implements all allocated requirements'))
    s.append(check('Interfaces completely and correctly specified'))
    s.append(check('Algorithms described with sufficient detail for independent implementation'))
    s.append(check('Error handling paths identified and specified'))
    s.append(check('Safety-related behavior documented'))
    s.append(check('Traceable to requirements (SRS-001) and risk controls (RMF-001)'))
    s.append(check('No contradictions with architecture or other designs'))
    s.append(check('SOUP usage appropriate and documented'))

    s.append(Paragraph('FINDINGS', ST['section']))
    s.append(table(
        ['#', 'Finding Description', 'Severity', 'Resolution Required', 'Status'],
        [['1', '', '', '', ''], ['2', '', '', '', ''], ['3', '', '', '', ''], ['4', '', '', '', '']],
        col_widths=[8*mm, 58*mm, 18*mm, 42*mm, 36*mm]
    ))

    s.append(Paragraph('CONCLUSION', ST['section']))
    s.append(check('APPROVED'))
    s.append(check('APPROVED WITH CONDITIONS'))
    s.append(check('NOT APPROVED — Redesign required'))
    s.append(field('Conditions / Comments', height=30))
    s.append(field_pair('Lead Reviewer Signature', 'Date'))


def t06_test_execution(s):
    s.append(Paragraph('TEST IDENTIFICATION', ST['section']))
    s.append(field_pair('Test ID', 'Test Level: Unit / Integration / System'))
    s.append(field('Requirement(s) Verified (REQ-IDs)'))
    s.append(field_pair('Software Version / Git SHA', 'Date'))
    s.append(field('Test Environment (browser, OS, backend version)'))
    s.append(field('Tester Name'))

    s.append(Paragraph('TEST PROCEDURE', ST['section']))
    s.append(field('Preconditions', height=25))
    s.append(field('Test Steps', height=60))

    s.append(Paragraph('RESULTS', ST['section']))
    s.append(field('Expected Result', height=25))
    s.append(field('Actual Result', height=25))
    s.append(Spacer(1, 4))
    s.append(check('PASS'))
    s.append(check('FAIL'))
    s.append(field('Anomalies Discovered', height=25))

    s.append(Paragraph('SIGN-OFF', ST['section']))
    s.append(field_pair('Tester Signature', 'Date'))


def t07_soup_vuln(s):
    s.append(Paragraph('REVIEW INFORMATION', ST['section']))
    s.append(field_pair('Review Period', 'Reviewed By'))
    s.append(field('Date'))

    s.append(Paragraph('AUTOMATED SCAN RESULTS', ST['section']))
    s.append(field_pair('npm audit — High/Critical Count', 'pip-audit — High/Critical Count'))
    s.append(field('CI Pipeline Run ID / Date'))

    s.append(Paragraph('CLASS C SOUP MANUAL NVD REVIEW', ST['section']))
    s.append(table(
        ['SOUP ID', 'Name', 'Version', 'New CVEs Found?', 'Action Required'],
        [
            ['SOUP-FE-008', 'ONNX Runtime Web', '1.21.0', '', ''],
            ['SOUP-BE-004', 'nibabel', '5.3.0', '', ''],
            ['SOUP-BE-005', 'pydicom', '2.4.4', '', ''],
            ['SOUP-BE-007', 'NumPy', '1.26.4', '', ''],
            ['SOUP-BE-008', 'SciPy', '1.13.1', '', ''],
            ['SOUP-BE-011', 'Anthropic SDK', '0.44.0', '', ''],
            ['SOUP-BE-012', 'Google Cloud AI', '1.136.0', '', ''],
        ],
        col_widths=[22*mm, 32*mm, 18*mm, 42*mm, 48*mm]
    ))

    s.append(Paragraph('REMEDIATION ACTIONS', ST['section']))
    s.append(table(
        ['CVE ID', 'SOUP Item', 'CVSS', 'Remediation Plan', 'Target Date', 'Owner'],
        [['', '', '', '', '', ''], ['', '', '', '', '', ''], ['', '', '', '', '', '']],
        col_widths=[24*mm, 24*mm, 14*mm, 42*mm, 24*mm, 34*mm]
    ))
    s.append(field_pair('Reviewer Signature', 'Date'))


def t08_incident(s):
    s.append(Paragraph('INCIDENT IDENTIFICATION', ST['section']))
    s.append(field_pair('Incident ID', 'Date Identified'))
    s.append(field_pair('Reported By', 'Software Version'))
    s.append(Spacer(1, 4))
    s.append(Paragraph('Severity:', ST['label']))
    s.append(check('Death'))
    s.append(check('Serious deterioration of health'))
    s.append(check('Potential for serious deterioration'))

    s.append(Paragraph('INCIDENT DESCRIPTION', ST['section']))
    s.append(field('Description of the Incident', height=50))
    s.append(field('Patient / User Impact', height=30))
    s.append(field('Affected Users (count / estimate)'))

    s.append(Paragraph('REGULATORY NOTIFICATION (EU MDR Article 87)', ST['section']))
    s.append(field_pair('Competent Authority: BfArM / Other', 'Notification Date'))
    s.append(check('Initial report submitted to EUDAMED'))
    s.append(check('Follow-up report submitted'))

    s.append(Paragraph('INVESTIGATION', ST['section']))
    s.append(field('Root Cause Analysis', height=40))
    s.append(field('Immediate Actions Taken', height=30))
    s.append(field('Corrective Actions Planned', height=30))
    s.append(check('Field Safety Notice issued'))
    s.append(check('Recall initiated'))

    s.append(Paragraph('STATUS', ST['section']))
    s.append(check('Reported'))
    s.append(check('Under investigation'))
    s.append(check('Resolved'))
    s.append(check('Closed'))
    s.append(field_pair('Investigator Signature', 'Date'))


def t09_change_control(s):
    s.append(Paragraph('CHANGE IDENTIFICATION', ST['section']))
    s.append(field_pair('Change ID / PR #', 'Date'))
    s.append(field('Requestor'))
    s.append(field('Description of Change', height=35))

    s.append(Paragraph('IMPACT ANALYSIS', ST['section']))
    s.append(field('Affected Requirements (REQ-IDs)'))
    s.append(field('Affected Design Documents (DD-IDs)'))
    s.append(field('Affected Risk Controls (RC-IDs)'))
    s.append(check('Safety impact identified — RMF-001 update required'))
    s.append(check('SOUP changes — SOUP-001 update required'))
    s.append(check('No safety or SOUP impact'))

    s.append(Paragraph('VERIFICATION', ST['section']))
    s.append(check('Unit tests PASS'))
    s.append(check('Integration tests PASS'))
    s.append(check('CI pipeline GREEN'))
    s.append(check('Code review approved (Reviewer: ______________________)'))
    s.append(check('Regression testing completed'))
    s.append(check('test_endpoints.sh 9/9 PASS'))

    s.append(Paragraph('APPROVAL', ST['section']))
    s.append(field_pair('Approved By', 'Approval Date'))
    s.append(field('Included in Release Version'))
    s.append(field('Signature'))


def t10_quality_gate(s):
    s.append(Paragraph('GATE IDENTIFICATION', ST['section']))
    s.append(Paragraph('Select Gate:', ST['label']))
    s.append(check('G1: Requirements Approved'))
    s.append(check('G2: Design Approved'))
    s.append(check('G3: Implementation Complete'))
    s.append(check('G4: Integration Verified'))
    s.append(check('G5: Release Approved'))
    s.append(field_pair('Feature / Release', 'Date'))

    s.append(Paragraph('ENTRY CRITERIA VERIFICATION', ST['section']))
    s.append(check('All planned deliverables for this phase complete'))
    s.append(check('All required reviews conducted and documented'))
    s.append(check('All tests at this level pass'))
    s.append(check('Risk analysis updated (if new features/changes)'))
    s.append(check('No critical or major open issues blocking gate'))
    s.append(check('Documentation current and version-controlled'))

    s.append(Paragraph('ISSUES AND CONDITIONS', ST['section']))
    s.append(field('Issues Blocking Gate', height=25))
    s.append(field('Conditions for Approval', height=25))

    s.append(Paragraph('DECISION', ST['section']))
    s.append(check('GATE PASSED'))
    s.append(check('GATE PASSED WITH CONDITIONS'))
    s.append(check('GATE FAILED — Return to previous phase'))
    s.append(field_pair('Authority / Approver', 'Date'))
    s.append(field('Signature'))


def t11_doc_approval(s):
    s.append(Paragraph('DOCUMENT APPROVAL MATRIX', ST['section']))
    s.append(Paragraph('Record the formal review and approval of each IEC 62304 regulatory document.', ST['body']))
    s.append(Spacer(1, 4))
    docs = [
        ['IEC62304-MASTER-001', 'Master Compliance Document', '1.0', '', '', ''],
        ['SDP-001', 'Software Development Plan', '1.0', '', '', ''],
        ['SRS-001', 'Software Requirements Specification', '1.0', '', '', ''],
        ['RMF-001', 'Risk Management File', '1.0', '', '', ''],
        ['TM-001', 'Traceability Matrix', '1.0', '', '', ''],
        ['DD-001', 'Detailed Design Specification', '1.0', '', '', ''],
        ['CMP-001', 'Configuration Management Plan', '1.0', '', '', ''],
        ['SPR-001', 'Problem Resolution Procedure', '1.0', '', '', ''],
        ['SOUP-001', 'SOUP Bill of Materials', '1.0', '', '', ''],
        ['VVP-001', 'Verification & Validation Plan', '1.0', '', '', ''],
        ['SMP-001', 'Maintenance Plan', '1.0', '', '', ''],
        ['CSA-001', 'Cybersecurity Assessment', '1.0', '', '', ''],
        ['REL-001', 'Release Procedure', '1.0', '', '', ''],
        ['SEG-001', 'Segregation Analysis', '1.0', '', '', ''],
    ]
    s.append(table(
        ['Doc ID', 'Title', 'Ver', 'Reviewed By', 'Approved By', 'Date'],
        docs,
        col_widths=[30*mm, 46*mm, 12*mm, 28*mm, 28*mm, 18*mm]
    ))

    s.append(Paragraph('APPROVAL AUTHORITY STATEMENT', ST['section']))
    s.append(Paragraph(
        'I confirm that the above documents have been reviewed for completeness, accuracy, and '
        'compliance with IEC 62304:2006+A1:2015, IEC 81001-5-1:2021, ISO 14971:2019, '
        'IEC 62366-1:2015+A1:2020, and applicable EU MDR 2017/745 requirements. '
        'All referenced standards are current editions as verified against the IEC Webstore '
        'and EU Official Journal harmonized standards list.',
        ST['body']
    ))
    s.append(Spacer(1, 8))
    s.append(field_pair('Name', 'Title / Role'))
    s.append(field('Organization'))
    s.append(field('Signature'))
    s.append(field('Date'))


# ═══════════════════════════════════════════════════════════════
# GENERATE
# ═══════════════════════════════════════════════════════════════

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print('Generating IEC 62304 Class C PDF Templates (Premium Design)...\n')

    templates = [
        ('TPL-01_Problem_Report.pdf', 'Software Problem Report', 'TPL-SPR-001', 'SPR-001', t01_problem_report),
        ('TPL-02_Release_Checklist.pdf', 'Pre-Release Verification Checklist', 'TPL-REL-001', 'REL-001', t02_release_checklist),
        ('TPL-03_Code_Review_Checklist.pdf', 'Code Review Checklist', 'TPL-CR-001', 'CMP-001', t03_code_review),
        ('TPL-04_Risk_Control_Verification.pdf', 'Risk Control Verification Record', 'TPL-RCV-001', 'RMF-001', t04_risk_control),
        ('TPL-05_Design_Review_Record.pdf', 'Design Review Record', 'TPL-DR-001', 'VVP-001', t05_design_review),
        ('TPL-06_Test_Execution_Report.pdf', 'Test Execution Report', 'TPL-TER-001', 'VVP-001', t06_test_execution),
        ('TPL-07_SOUP_Vulnerability_Review.pdf', 'SOUP Vulnerability Monitoring Record', 'TPL-SOUP-001', 'SMP-001', t07_soup_vuln),
        ('TPL-08_Serious_Incident_Report.pdf', 'Serious Incident Report (EU MDR Art. 87)', 'TPL-SIR-001', 'SMP-001', t08_incident),
        ('TPL-09_Change_Control_Record.pdf', 'Change Control Record', 'TPL-CCR-001', 'CMP-001', t09_change_control),
        ('TPL-10_Quality_Gate_Approval.pdf', 'Quality Gate Approval Record', 'TPL-QGA-001', 'SDP-001', t10_quality_gate),
        ('TPL-11_Document_Approval.pdf', 'Document Approval & Release Record', 'TPL-DAR-001', 'All Documents', t11_doc_approval),
    ]

    for fn, title, doc_id, parent, content in templates:
        build(fn, title, doc_id, parent, content)

    print(f'\nDone! {len(templates)} premium PDF templates generated.')


if __name__ == '__main__':
    main()
