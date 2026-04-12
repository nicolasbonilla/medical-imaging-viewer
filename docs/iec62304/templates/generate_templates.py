"""
Generate all IEC 62304 Class C fillable PDF templates.

Creates professional, audit-ready PDF forms for MSTool-AI
regulatory documentation. Each template includes:
- MSTool-AI branding header
- Document control fields
- Fillable form fields with clear labels
- Reference to parent IEC 62304 document
- Footer with classification and version

Uses ReportLab for PDF generation.
"""

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.colors import HexColor, black, white
from reportlab.lib.units import mm
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, HRFlowable,
)
from reportlab.platypus.flowables import Flowable
import os
from datetime import datetime

# ─── Design Constants ───
NAVY = HexColor('#0F172A')
DARK_NAVY = HexColor('#0A0F1E')
TEAL = HexColor('#0D9488')
BLUE = HexColor('#3B82F6')
LIGHT_GRAY = HexColor('#F1F5F9')
MED_GRAY = HexColor('#94A3B8')
DARK_GRAY = HexColor('#334155')
BORDER = HexColor('#CBD5E1')
TABLE_HEADER = HexColor('#1E3A5F')
TABLE_ALT = HexColor('#F8FAFC')

PAGE_W, PAGE_H = A4
MARGIN = 20 * mm
CONTENT_W = PAGE_W - 2 * MARGIN

OUTPUT_DIR = os.path.dirname(__file__)


# ─── Styles ───
def S(name, **kwargs):
    defaults = dict(fontName='Helvetica', fontSize=9, textColor=DARK_GRAY, leading=12)
    defaults.update(kwargs)
    return ParagraphStyle(name, **defaults)

STYLES = {
    'title': S('title', fontName='Helvetica-Bold', fontSize=16, textColor=NAVY, alignment=TA_CENTER, spaceAfter=4),
    'subtitle': S('subtitle', fontName='Helvetica', fontSize=10, textColor=MED_GRAY, alignment=TA_CENTER, spaceAfter=12),
    'section': S('section', fontName='Helvetica-Bold', fontSize=11, textColor=NAVY, spaceBefore=14, spaceAfter=6),
    'body': S('body', fontSize=9, textColor=DARK_GRAY, spaceAfter=4, leading=12),
    'small': S('small', fontSize=7, textColor=MED_GRAY, leading=9),
    'th': S('th', fontName='Helvetica-Bold', fontSize=7.5, textColor=white, leading=10),
    'td': S('td', fontSize=8, textColor=DARK_GRAY, leading=10),
    'field_label': S('fl', fontName='Helvetica-Bold', fontSize=8, textColor=DARK_GRAY),
    'field_value': S('fv', fontSize=9, textColor=HexColor('#1E293B'), leading=12),
    'footer': S('footer', fontSize=6.5, textColor=MED_GRAY, alignment=TA_CENTER),
}


# ─── Helpers ───
def header_footer(canvas, doc, title, doc_id):
    canvas.saveState()
    # Header line
    canvas.setStrokeColor(TEAL)
    canvas.setLineWidth(1.5)
    canvas.line(MARGIN, PAGE_H - 15 * mm, PAGE_W - MARGIN, PAGE_H - 15 * mm)
    # Header text
    canvas.setFillColor(NAVY)
    canvas.setFont('Helvetica-Bold', 8)
    canvas.drawString(MARGIN, PAGE_H - 13 * mm, 'MSTool-AI')
    canvas.setFillColor(MED_GRAY)
    canvas.setFont('Helvetica', 7)
    canvas.drawRightString(PAGE_W - MARGIN, PAGE_H - 13 * mm, f'{doc_id} | {title}')
    # Footer
    canvas.setStrokeColor(BORDER)
    canvas.setLineWidth(0.4)
    canvas.line(MARGIN, 12 * mm, PAGE_W - MARGIN, 12 * mm)
    canvas.setFillColor(MED_GRAY)
    canvas.setFont('Helvetica', 6)
    canvas.drawString(MARGIN, 8 * mm, 'IEC 62304:2006+A1:2015 Class C | IEC 81001-5-1:2021 | CONFIDENTIAL')
    canvas.drawRightString(PAGE_W - MARGIN, 8 * mm, f'Page {doc.page}')
    canvas.restoreState()


def make_table(headers, rows, col_widths=None):
    header_cells = [Paragraph(h, STYLES['th']) for h in headers]
    data = [header_cells]
    for row in rows:
        data.append([Paragraph(str(c), STYLES['td']) for c in row])
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
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('GRID', (0, 0), (-1, -1), 0.4, BORDER),
        ('LINEBELOW', (0, 0), (-1, 0), 1.5, TEAL),
    ]
    for i in range(1, len(data)):
        if i % 2 == 0:
            cmds.append(('BACKGROUND', (0, i), (-1, i), TABLE_ALT))
    t.setStyle(TableStyle(cmds))
    return t


def field_row(label, value='', width_ratio=0.3):
    lw = CONTENT_W * width_ratio
    vw = CONTENT_W * (1 - width_ratio)
    data = [[Paragraph(f'<b>{label}:</b>', STYLES['field_label']),
             Paragraph(value or '_______________________________________________', STYLES['field_value'])]]
    t = Table(data, colWidths=[lw, vw])
    t.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LINEBELOW', (1, 0), (1, 0), 0.3, BORDER),
    ]))
    return t


def build_template(filename, title, doc_id, parent_ref, content_fn):
    path = os.path.join(OUTPUT_DIR, filename)
    doc = SimpleDocTemplate(path, pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN,
                            topMargin=25 * mm, bottomMargin=20 * mm,
                            title=title, author='MSTool-AI')
    story = []

    # Title block
    story.append(Paragraph(title, STYLES['title']))
    story.append(Paragraph(f'{doc_id} | IEC 62304 Class C | Parent: {parent_ref}', STYLES['subtitle']))
    story.append(HRFlowable(width=CONTENT_W, thickness=1.5, color=TEAL))
    story.append(Spacer(1, 8))

    # Document control
    story.append(Paragraph('Document Control', STYLES['section']))
    story.append(field_row('Document ID', doc_id))
    story.append(field_row('Version'))
    story.append(field_row('Date'))
    story.append(field_row('Prepared By'))
    story.append(field_row('Reviewed By'))
    story.append(field_row('Approved By'))
    story.append(Spacer(1, 10))

    # Content
    content_fn(story)

    # Footer note
    story.append(Spacer(1, 15))
    story.append(HRFlowable(width=CONTENT_W, thickness=0.4, color=BORDER))
    story.append(Paragraph(
        f'This document is part of the MSTool-AI IEC 62304 Class C regulatory documentation suite. '
        f'Generated {datetime.now().strftime("%Y-%m-%d")}. Maintain under configuration management.',
        STYLES['small']
    ))

    doc.build(story, onFirstPage=lambda c, d: header_footer(c, d, title, doc_id),
              onLaterPages=lambda c, d: header_footer(c, d, title, doc_id))
    print(f'  Created: {filename}')


# ═══════════════════════════════════════════════════════════════
# TEMPLATE DEFINITIONS
# ═══════════════════════════════════════════════════════════════

def tmpl_problem_report(story):
    story.append(Paragraph('Problem Description', STYLES['section']))
    story.append(field_row('Problem ID', '(Auto-generated)'))
    story.append(field_row('Reporter'))
    story.append(field_row('Date'))
    story.append(field_row('Software Version / Git SHA'))
    story.append(field_row('Severity', '[ ] Critical  [ ] Major  [ ] Minor'))
    story.append(Spacer(1, 6))
    story.append(field_row('Description'))
    story.append(Spacer(1, 20))
    story.append(field_row('Steps to Reproduce'))
    story.append(Spacer(1, 20))
    story.append(field_row('Expected Behavior'))
    story.append(Spacer(1, 10))
    story.append(field_row('Actual Behavior'))
    story.append(Spacer(1, 10))

    story.append(Paragraph('Safety Impact Assessment', STYLES['section']))
    story.append(Paragraph('[ ] Could contribute to a hazardous situation (reference HAZ-ID: ________)', STYLES['body']))
    story.append(Paragraph('[ ] Affects a Class C software item (specify: ________________)', STYLES['body']))
    story.append(Paragraph('[ ] Requires regulatory notification (EU MDR Article 87)', STYLES['body']))
    story.append(Spacer(1, 10))

    story.append(Paragraph('Investigation & Resolution', STYLES['section']))
    story.append(field_row('Root Cause'))
    story.append(Spacer(1, 15))
    story.append(field_row('Affected Software Items'))
    story.append(field_row('Fix Description'))
    story.append(Spacer(1, 15))
    story.append(field_row('Fix Commit SHA'))
    story.append(field_row('Regression Test Result', '[ ] PASS  [ ] FAIL'))
    story.append(field_row('Closed By'))
    story.append(field_row('Close Date'))


def tmpl_release_checklist(story):
    story.append(Paragraph('Release Information', STYLES['section']))
    story.append(field_row('Release Version'))
    story.append(field_row('Release Date'))
    story.append(field_row('Release Manager'))
    story.append(Spacer(1, 8))

    story.append(Paragraph('Pre-Release Verification (IEC 62304 Clause 5.8.1)', STYLES['section']))
    checks = [
        ['[ ]', 'All unit tests pass (Class C units)', '', ''],
        ['[ ]', 'Integration tests pass (test_endpoints.sh 9/9)', '', ''],
        ['[ ]', 'TypeScript compilation successful (npx tsc --noEmit)', '', ''],
        ['[ ]', 'Python syntax check passes (all .py files)', '', ''],
        ['[ ]', 'Code review completed for all changes since last release', '', ''],
        ['[ ]', 'No critical/major open bugs (GitHub Issues reviewed)', '', ''],
        ['[ ]', 'Risk analysis updated (if applicable) — RMF-001', '', ''],
        ['[ ]', 'SOUP list updated (if dependencies changed) — SOUP-001', '', ''],
        ['[ ]', 'Traceability matrix updated — TM-001', '', ''],
        ['[ ]', 'SOUP vulnerability scan clean (npm audit + pip-audit)', '', ''],
        ['[ ]', 'Known anomalies documented (Section below)', '', ''],
    ]
    story.append(make_table(
        ['Check', 'Item', 'Evidence', 'Verified By'],
        checks,
        col_widths=[12*mm, 85*mm, 40*mm, 25*mm]
    ))
    story.append(Spacer(1, 8))

    story.append(Paragraph('Known Residual Anomalies (IEC 62304 Clause 5.8.2)', STYLES['section']))
    story.append(make_table(
        ['Anomaly ID', 'Description', 'Severity', 'Safety Impact', 'Disposition'],
        [['', '', '', '', ''], ['', '', '', '', ''], ['', '', '', '', '']],
        col_widths=[20*mm, 55*mm, 20*mm, 25*mm, 42*mm]
    ))
    story.append(Spacer(1, 8))

    story.append(Paragraph('Deployment Record', STYLES['section']))
    story.append(field_row('Backend Build ID'))
    story.append(field_row('Backend Deploy Time'))
    story.append(field_row('Frontend Deploy Version'))
    story.append(field_row('Frontend Deploy Time'))
    story.append(field_row('Post-Deploy test_endpoints.sh', '[ ] 9/9 PASS  [ ] FAIL'))
    story.append(Spacer(1, 8))

    story.append(Paragraph('Approval', STYLES['section']))
    story.append(field_row('Release Approved By'))
    story.append(field_row('Approval Date'))
    story.append(field_row('Signature'))


def tmpl_code_review(story):
    story.append(Paragraph('Review Context', STYLES['section']))
    story.append(field_row('Review ID'))
    story.append(field_row('Module / Software Unit'))
    story.append(field_row('Pull Request #'))
    story.append(field_row('Author'))
    story.append(field_row('Reviewer'))
    story.append(field_row('Date'))
    story.append(field_row('Safety Class of Unit', '[ ] A  [ ] B  [ ] C'))
    story.append(Spacer(1, 8))

    story.append(Paragraph('Code Review Checklist (IEC 62304 Clause 5.5.3, 5.5.4)', STYLES['section']))
    checks = [
        ['[ ]', 'Code implements the detailed design specification (DD-001)'],
        ['[ ]', 'Coding standards followed (ESLint / PEP 8)'],
        ['[ ]', 'No commented-out code without linked issue'],
        ['[ ]', 'Input validation present for all external inputs'],
        ['[ ]', 'Error handling covers all failure modes from design'],
        ['[ ]', 'No unhandled exceptions/promise rejections'],
        ['[ ]', 'Safety-critical calculations verified (units, ranges, overflow)'],
        ['[ ]', 'Risk control measures correctly implemented (HAZ-IDs: _____)'],
        ['[ ]', 'No hardcoded credentials or secrets'],
        ['[ ]', 'Authentication/authorization checked on endpoints'],
        ['[ ]', 'Functions under 50 lines (or justified)'],
        ['[ ]', 'Named constants instead of magic numbers'],
        ['[ ]', 'Unit tests present for new/modified code'],
        ['[ ]', 'All tests pass locally and in CI'],
        ['[ ]', 'No unintended functionality (Class C requirement)'],
        ['[ ]', 'Robustness with invalid inputs verified (Class C)'],
        ['[ ]', 'SOUP APIs used correctly per documentation'],
    ]
    story.append(make_table(
        ['Check', 'Criterion'],
        checks,
        col_widths=[12*mm, CONTENT_W - 12*mm]
    ))
    story.append(Spacer(1, 8))

    story.append(Paragraph('Result', STYLES['section']))
    story.append(Paragraph('[ ] APPROVED    [ ] APPROVED WITH COMMENTS    [ ] REJECTED', STYLES['body']))
    story.append(Spacer(1, 6))
    story.append(field_row('Comments'))
    story.append(Spacer(1, 25))
    story.append(field_row('Reviewer Signature'))
    story.append(field_row('Author Acknowledgment'))


def tmpl_risk_control_verification(story):
    story.append(Paragraph('Risk Control Verification Record (ISO 14971 + IEC 62304 Clause 7.3)', STYLES['section']))
    story.append(Spacer(1, 4))

    story.append(field_row('Risk Control ID', 'RC-____'))
    story.append(field_row('Hazard Reference', 'HAZ-____'))
    story.append(field_row('Requirement Reference', 'REQ-SAFE-____'))
    story.append(field_row('Risk Control Description'))
    story.append(Spacer(1, 10))
    story.append(field_row('Implementation Location', '(file path and line)'))
    story.append(Spacer(1, 6))

    story.append(Paragraph('Verification Method', STYLES['section']))
    story.append(Paragraph('[ ] Test (automated)  [ ] Test (manual)  [ ] Code Inspection  [ ] Analysis', STYLES['body']))
    story.append(Spacer(1, 6))
    story.append(field_row('Test ID (if applicable)'))
    story.append(field_row('Test Procedure'))
    story.append(Spacer(1, 15))
    story.append(field_row('Expected Result'))
    story.append(Spacer(1, 10))
    story.append(field_row('Actual Result'))
    story.append(Spacer(1, 10))

    story.append(Paragraph('Conclusion', STYLES['section']))
    story.append(Paragraph('[ ] PASS — Risk control effective    [ ] FAIL — Risk control NOT effective', STYLES['body']))
    story.append(Spacer(1, 6))
    story.append(field_row('Verified By'))
    story.append(field_row('Verification Date'))
    story.append(field_row('Signature'))


def tmpl_design_review(story):
    story.append(Paragraph('Design Review Record (IEC 62304 Clause 5.3.6, 5.4.4)', STYLES['section']))
    story.append(Spacer(1, 4))

    story.append(field_row('Review Type', '[ ] Architecture  [ ] Detailed Design (Class C)'))
    story.append(field_row('Document Reviewed', '(e.g., DD-AI-001, SAD Section 2)'))
    story.append(field_row('Review Date'))
    story.append(field_row('Reviewer(s)'))
    story.append(Spacer(1, 8))

    story.append(Paragraph('Review Checklist', STYLES['section']))
    checks = [
        ['[ ]', 'Design implements all allocated requirements'],
        ['[ ]', 'Interfaces completely and correctly specified'],
        ['[ ]', 'Algorithms described with sufficient detail for implementation'],
        ['[ ]', 'Error handling paths identified and specified'],
        ['[ ]', 'Safety-related behavior documented'],
        ['[ ]', 'Traceable to requirements (SRS-001) and risk controls (RMF-001)'],
        ['[ ]', 'No contradictions with architecture or other designs'],
        ['[ ]', 'SOUP usage appropriate and documented'],
    ]
    story.append(make_table(['Check', 'Criterion'], checks, col_widths=[12*mm, CONTENT_W - 12*mm]))
    story.append(Spacer(1, 8))

    story.append(Paragraph('Findings', STYLES['section']))
    story.append(make_table(
        ['#', 'Finding', 'Severity', 'Resolution', 'Status'],
        [['1', '', '', '', ''], ['2', '', '', '', ''], ['3', '', '', '', '']],
        col_widths=[8*mm, 60*mm, 20*mm, 45*mm, 29*mm]
    ))
    story.append(Spacer(1, 8))

    story.append(Paragraph('Conclusion', STYLES['section']))
    story.append(Paragraph('[ ] APPROVED    [ ] APPROVED WITH CONDITIONS    [ ] NOT APPROVED', STYLES['body']))
    story.append(field_row('Conditions (if any)'))
    story.append(Spacer(1, 15))
    story.append(field_row('Lead Reviewer Signature'))
    story.append(field_row('Date'))


def tmpl_test_execution(story):
    story.append(Paragraph('Test Execution Report (IEC 62304 Clause 5.7, 9.8)', STYLES['section']))
    story.append(Spacer(1, 4))

    story.append(field_row('Test ID'))
    story.append(field_row('Test Level', '[ ] Unit  [ ] Integration  [ ] System'))
    story.append(field_row('Requirement(s) Verified'))
    story.append(field_row('Software Version / Git SHA'))
    story.append(field_row('Test Environment'))
    story.append(field_row('Tester'))
    story.append(field_row('Date'))
    story.append(Spacer(1, 8))

    story.append(Paragraph('Test Procedure', STYLES['section']))
    story.append(Paragraph('Preconditions:', STYLES['field_label']))
    story.append(Spacer(1, 15))
    story.append(Paragraph('Steps:', STYLES['field_label']))
    story.append(Spacer(1, 40))

    story.append(Paragraph('Results', STYLES['section']))
    story.append(field_row('Expected Result'))
    story.append(Spacer(1, 15))
    story.append(field_row('Actual Result'))
    story.append(Spacer(1, 15))
    story.append(Paragraph('[ ] PASS    [ ] FAIL', STYLES['body']))
    story.append(Spacer(1, 6))
    story.append(field_row('Anomalies Discovered'))
    story.append(Spacer(1, 15))
    story.append(field_row('Tester Signature'))
    story.append(field_row('Date'))


def tmpl_soup_vulnerability(story):
    story.append(Paragraph('SOUP Vulnerability Monitoring Record (IEC 81001-5-1 Clause 5.3.12)', STYLES['section']))
    story.append(Spacer(1, 4))

    story.append(field_row('Review Period'))
    story.append(field_row('Reviewed By'))
    story.append(field_row('Date'))
    story.append(Spacer(1, 8))

    story.append(Paragraph('Automated Scan Results', STYLES['section']))
    story.append(field_row('npm audit — High severity count'))
    story.append(field_row('npm audit — Critical severity count'))
    story.append(field_row('pip-audit — High severity count'))
    story.append(field_row('pip-audit — Critical severity count'))
    story.append(Spacer(1, 8))

    story.append(Paragraph('Class C SOUP Manual NVD Review', STYLES['section']))
    soup_items = [
        ['SOUP-FE-008', 'ONNX Runtime Web', '1.21.0', '', ''],
        ['SOUP-BE-004', 'nibabel', '5.3.0', '', ''],
        ['SOUP-BE-005', 'pydicom', '2.4.4', '', ''],
        ['SOUP-BE-007', 'NumPy', '1.26.4', '', ''],
        ['SOUP-BE-008', 'SciPy', '1.13.1', '', ''],
        ['SOUP-BE-011', 'Anthropic SDK', '0.44.0', '', ''],
        ['SOUP-BE-012', 'Google Cloud AI', '1.136.0', '', ''],
    ]
    story.append(make_table(
        ['SOUP ID', 'Name', 'Version', 'New CVEs?', 'Action Required'],
        soup_items,
        col_widths=[22*mm, 35*mm, 20*mm, 40*mm, 45*mm]
    ))
    story.append(Spacer(1, 8))

    story.append(Paragraph('Actions Required', STYLES['section']))
    story.append(make_table(
        ['CVE ID', 'SOUP Item', 'CVSS', 'Remediation', 'Target Date', 'Owner'],
        [['', '', '', '', '', ''], ['', '', '', '', '', '']],
        col_widths=[25*mm, 25*mm, 15*mm, 45*mm, 25*mm, 27*mm]
    ))
    story.append(Spacer(1, 8))
    story.append(field_row('Reviewer Signature'))
    story.append(field_row('Date'))


def tmpl_incident_report(story):
    story.append(Paragraph('Serious Incident Report (EU MDR Article 87)', STYLES['section']))
    story.append(Spacer(1, 4))

    story.append(field_row('Incident ID'))
    story.append(field_row('Date Identified'))
    story.append(field_row('Reported By'))
    story.append(field_row('Severity', '[ ] Death  [ ] Serious deterioration of health  [ ] Other'))
    story.append(Spacer(1, 6))
    story.append(field_row('Problem Description'))
    story.append(Spacer(1, 20))
    story.append(field_row('Patient Impact'))
    story.append(Spacer(1, 10))
    story.append(field_row('Affected Users (count/estimate)'))
    story.append(Spacer(1, 8))

    story.append(Paragraph('Regulatory Notification', STYLES['section']))
    story.append(field_row('Competent Authority', '[ ] BfArM  [ ] Other: ________'))
    story.append(field_row('Notification Date'))
    story.append(field_row('EUDAMED Submission', '[ ] Yes  [ ] N/A'))
    story.append(Spacer(1, 8))

    story.append(Paragraph('Investigation', STYLES['section']))
    story.append(field_row('Root Cause'))
    story.append(Spacer(1, 20))
    story.append(field_row('Immediate Actions Taken'))
    story.append(Spacer(1, 15))
    story.append(field_row('Corrective Actions Planned'))
    story.append(Spacer(1, 15))
    story.append(field_row('Field Safety Notice Issued', '[ ] Yes  [ ] No'))
    story.append(field_row('Status', '[ ] Reported  [ ] Under investigation  [ ] Resolved  [ ] Closed'))
    story.append(Spacer(1, 8))
    story.append(field_row('Investigator Signature'))
    story.append(field_row('Date'))


def tmpl_change_control(story):
    story.append(Paragraph('Change Control Record (IEC 62304 Clause 8.2)', STYLES['section']))
    story.append(Spacer(1, 4))

    story.append(field_row('Change ID / PR #'))
    story.append(field_row('Date'))
    story.append(field_row('Requestor'))
    story.append(field_row('Description of Change'))
    story.append(Spacer(1, 15))

    story.append(Paragraph('Impact Analysis', STYLES['section']))
    story.append(field_row('Affected Requirements', '(REQ-IDs)'))
    story.append(field_row('Affected Design', '(DD-IDs)'))
    story.append(field_row('Affected Risk Controls', '(RC-IDs)'))
    story.append(field_row('Safety Impact', '[ ] Yes  [ ] No  — If yes, update RMF-001'))
    story.append(field_row('SOUP Changes', '[ ] Yes  [ ] No  — If yes, update SOUP-001'))
    story.append(Spacer(1, 8))

    story.append(Paragraph('Verification', STYLES['section']))
    story.append(field_row('Unit Tests', '[ ] Pass  [ ] Fail  [ ] N/A'))
    story.append(field_row('Integration Tests', '[ ] Pass  [ ] Fail  [ ] N/A'))
    story.append(field_row('CI Pipeline', '[ ] Green  [ ] Red'))
    story.append(field_row('Code Review Approval', '[ ] Yes  Reviewer: ___________'))
    story.append(field_row('Regression Testing', '[ ] Done  [ ] Not required'))
    story.append(Spacer(1, 8))

    story.append(Paragraph('Approval', STYLES['section']))
    story.append(field_row('Approved By'))
    story.append(field_row('Approval Date'))
    story.append(field_row('Included in Release'))


def tmpl_quality_gate(story):
    story.append(Paragraph('Quality Gate Approval Record (SDP-001 Section 3.3)', STYLES['section']))
    story.append(Spacer(1, 4))

    story.append(field_row('Gate ID', '[ ] G1: Reqs Approved  [ ] G2: Design Approved  [ ] G3: Impl Complete  [ ] G4: Integration  [ ] G5: Release'))
    story.append(field_row('Feature / Release'))
    story.append(field_row('Date'))
    story.append(Spacer(1, 8))

    story.append(Paragraph('Entry Criteria', STYLES['section']))
    checks = [
        ['[ ]', 'All planned deliverables for this phase complete'],
        ['[ ]', 'All required reviews conducted and documented'],
        ['[ ]', 'All tests at this level pass'],
        ['[ ]', 'Risk analysis updated (if new features/changes)'],
        ['[ ]', 'No critical or major open issues blocking gate'],
        ['[ ]', 'Documentation current and version-controlled'],
    ]
    story.append(make_table(['Check', 'Criterion'], checks, col_widths=[12*mm, CONTENT_W - 12*mm]))
    story.append(Spacer(1, 8))

    story.append(field_row('Issues Blocking Gate'))
    story.append(Spacer(1, 10))
    story.append(field_row('Conditions for Approval'))
    story.append(Spacer(1, 10))

    story.append(Paragraph('Decision', STYLES['section']))
    story.append(Paragraph('[ ] GATE PASSED    [ ] GATE PASSED WITH CONDITIONS    [ ] GATE FAILED', STYLES['body']))
    story.append(Spacer(1, 8))
    story.append(field_row('Authority / Approver'))
    story.append(field_row('Signature'))
    story.append(field_row('Date'))


def tmpl_document_approval(story):
    story.append(Paragraph('Document Approval Record', STYLES['section']))
    story.append(Paragraph('For formal approval of IEC 62304 regulatory documents', STYLES['small']))
    story.append(Spacer(1, 8))

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
    story.append(make_table(
        ['Doc ID', 'Title', 'Version', 'Reviewed By', 'Approved By', 'Date'],
        docs,
        col_widths=[28*mm, 48*mm, 14*mm, 28*mm, 28*mm, 16*mm]
    ))
    story.append(Spacer(1, 12))

    story.append(Paragraph('Approval Authority Statement', STYLES['section']))
    story.append(Paragraph(
        'I confirm that the above documents have been reviewed for completeness, accuracy, '
        'and compliance with IEC 62304:2006+A1:2015, IEC 81001-5-1:2021, ISO 14971:2019, '
        'and applicable EU MDR 2017/745 requirements.',
        STYLES['body']
    ))
    story.append(Spacer(1, 15))
    story.append(field_row('Name'))
    story.append(field_row('Title / Role'))
    story.append(field_row('Signature'))
    story.append(field_row('Date'))


# ═══════════════════════════════════════════════════════════════
# GENERATE ALL TEMPLATES
# ═══════════════════════════════════════════════════════════════

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print('Generating IEC 62304 Class C PDF templates...\n')

    templates = [
        ('TPL-01_Problem_Report.pdf', 'Software Problem Report', 'TPL-SPR-001', 'SPR-001', tmpl_problem_report),
        ('TPL-02_Release_Checklist.pdf', 'Pre-Release Verification Checklist', 'TPL-REL-001', 'REL-001', tmpl_release_checklist),
        ('TPL-03_Code_Review_Checklist.pdf', 'Code Review Checklist', 'TPL-CR-001', 'CMP-001 / VVP-001', tmpl_code_review),
        ('TPL-04_Risk_Control_Verification.pdf', 'Risk Control Verification Record', 'TPL-RCV-001', 'RMF-001', tmpl_risk_control_verification),
        ('TPL-05_Design_Review_Record.pdf', 'Design Review Record', 'TPL-DR-001', 'VVP-001', tmpl_design_review),
        ('TPL-06_Test_Execution_Report.pdf', 'Test Execution Report', 'TPL-TER-001', 'VVP-001 / TM-001', tmpl_test_execution),
        ('TPL-07_SOUP_Vulnerability_Review.pdf', 'SOUP Vulnerability Monitoring Record', 'TPL-SOUP-001', 'SMP-001 / SOUP-001', tmpl_soup_vulnerability),
        ('TPL-08_Serious_Incident_Report.pdf', 'Serious Incident Report (EU MDR Art. 87)', 'TPL-SIR-001', 'SMP-001', tmpl_incident_report),
        ('TPL-09_Change_Control_Record.pdf', 'Change Control Record', 'TPL-CCR-001', 'CMP-001', tmpl_change_control),
        ('TPL-10_Quality_Gate_Approval.pdf', 'Quality Gate Approval Record', 'TPL-QGA-001', 'SDP-001', tmpl_quality_gate),
        ('TPL-11_Document_Approval.pdf', 'Document Approval & Release Record', 'TPL-DAR-001', 'All IEC 62304 Documents', tmpl_document_approval),
    ]

    for filename, title, doc_id, parent, fn in templates:
        build_template(filename, title, doc_id, parent, fn)

    print(f'\nDone! {len(templates)} templates generated in {OUTPUT_DIR}/')


if __name__ == '__main__':
    main()
