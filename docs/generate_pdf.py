"""
Generate a professional PhD-level PDF technical document for the MS Brain MRI Viewer.

Uses ReportLab for high-quality PDF generation with:
- Professional academic typography (Helvetica family)
- Table of contents with page numbers
- Mathematical formulas
- Syntax-highlighted code blocks
- Professional tables with alternating row colors
- Headers/footers with page numbers
- Academic citation formatting
- Figure-quality diagrams
"""

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.colors import HexColor, black, white, Color
from reportlab.lib.units import mm, cm, inch
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, KeepTogether, HRFlowable, Image, Frame, PageTemplate,
    BaseDocTemplate, NextPageTemplate, Flowable
)
from reportlab.platypus.tableofcontents import TableOfContents
from reportlab.graphics.shapes import Drawing, Rect, String, Line, Circle, Polygon
from reportlab.graphics import renderPDF
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import os
import datetime

# ============================================================================
# COLOR PALETTE (Academic/Medical — Deep Navy + Teal accents)
# ============================================================================
NAVY = HexColor('#1B2A4A')
DARK_NAVY = HexColor('#0F1B33')
TEAL = HexColor('#0D9488')
LIGHT_TEAL = HexColor('#CCFBF1')
ACCENT_BLUE = HexColor('#3B82F6')
LIGHT_GRAY = HexColor('#F8FAFC')
MED_GRAY = HexColor('#94A3B8')
DARK_GRAY = HexColor('#334155')
TABLE_HEADER_BG = HexColor('#1E3A5F')
TABLE_ALT_ROW = HexColor('#F1F5F9')
CODE_BG = HexColor('#1E293B')
CODE_TEXT = HexColor('#E2E8F0')
BORDER_COLOR = HexColor('#CBD5E1')
RED_ACCENT = HexColor('#EF4444')
GREEN_ACCENT = HexColor('#22C55E')
YELLOW_ACCENT = HexColor('#F59E0B')

# ============================================================================
# PAGE SETUP
# ============================================================================
PAGE_WIDTH, PAGE_HEIGHT = A4
LEFT_MARGIN = 25 * mm
RIGHT_MARGIN = 25 * mm
TOP_MARGIN = 30 * mm
BOTTOM_MARGIN = 25 * mm
CONTENT_WIDTH = PAGE_WIDTH - LEFT_MARGIN - RIGHT_MARGIN

# ============================================================================
# CUSTOM FLOWABLES
# ============================================================================

class ColoredLine(Flowable):
    """Horizontal line with custom color and thickness."""
    def __init__(self, width, color=TEAL, thickness=1.5):
        Flowable.__init__(self)
        self.width = width
        self.color = color
        self.thickness = thickness
        self.height = thickness + 2

    def draw(self):
        self.canv.setStrokeColor(self.color)
        self.canv.setLineWidth(self.thickness)
        self.canv.line(0, 0, self.width, 0)


class GradientBox(Flowable):
    """Box with gradient background for section headers."""
    def __init__(self, width, height, text, style):
        Flowable.__init__(self)
        self.width = width
        self.box_height = height
        self.text = text
        self.style = style
        self.height = height

    def draw(self):
        # Gradient background
        steps = 20
        for i in range(steps):
            ratio = i / steps
            r = NAVY.red * (1 - ratio * 0.3)
            g = NAVY.green * (1 - ratio * 0.3)
            b = NAVY.blue * (1 - ratio * 0.1)
            self.canv.setFillColor(Color(r, g, b))
            y = self.box_height * (1 - (i + 1) / steps)
            h = self.box_height / steps + 0.5
            self.canv.rect(0, y, self.width, h, fill=1, stroke=0)

        # Teal accent bar at bottom
        self.canv.setFillColor(TEAL)
        self.canv.rect(0, 0, self.width, 2, fill=1, stroke=0)

        # Text
        self.canv.setFillColor(white)
        self.canv.setFont('Helvetica-Bold', 14)
        self.canv.drawString(15, self.box_height * 0.35, self.text)


class CodeBlock(Flowable):
    """Styled code block with dark background."""
    def __init__(self, code, width):
        Flowable.__init__(self)
        self.code = code
        self.block_width = width
        lines = code.strip().split('\n')
        self.line_height = 11
        self.padding = 10
        self.height = len(lines) * self.line_height + self.padding * 2 + 4

    def draw(self):
        # Background
        self.canv.setFillColor(CODE_BG)
        self.canv.roundRect(0, 0, self.block_width, self.height, 4, fill=1, stroke=0)

        # Left accent bar
        self.canv.setFillColor(TEAL)
        self.canv.rect(0, 0, 3, self.height, fill=1, stroke=0)

        # Code text
        self.canv.setFillColor(CODE_TEXT)
        self.canv.setFont('Courier', 7.5)
        lines = self.code.strip().split('\n')
        y = self.height - self.padding - self.line_height + 2
        for line in lines:
            self.canv.drawString(self.padding + 4, y, line[:95])
            y -= self.line_height


class FormulaBox(Flowable):
    """Mathematical formula display with light background."""
    def __init__(self, formula, width, label=None):
        Flowable.__init__(self)
        self.formula = formula
        self.block_width = width
        self.label = label
        self.height = 30

    def draw(self):
        # Light background
        self.canv.setFillColor(HexColor('#F0F9FF'))
        self.canv.roundRect(0, 0, self.block_width, self.height, 3, fill=1, stroke=0)

        # Border
        self.canv.setStrokeColor(HexColor('#BAE6FD'))
        self.canv.setLineWidth(0.5)
        self.canv.roundRect(0, 0, self.block_width, self.height, 3, fill=0, stroke=1)

        # Formula text
        self.canv.setFillColor(DARK_NAVY)
        self.canv.setFont('Courier-Bold', 9)
        self.canv.drawCentredString(self.block_width / 2, 10, self.formula)

        # Label
        if self.label:
            self.canv.setFillColor(MED_GRAY)
            self.canv.setFont('Helvetica', 7)
            self.canv.drawRightString(self.block_width - 8, 10, self.label)


# ============================================================================
# STYLES
# ============================================================================

def create_styles():
    styles = getSampleStyleSheet()

    styles.add(ParagraphStyle(
        'DocTitle', fontName='Helvetica-Bold', fontSize=22,
        textColor=NAVY, alignment=TA_CENTER, spaceAfter=6,
        leading=26
    ))
    styles.add(ParagraphStyle(
        'DocSubtitle', fontName='Helvetica', fontSize=11,
        textColor=DARK_GRAY, alignment=TA_CENTER, spaceAfter=4,
        leading=14
    ))
    styles.add(ParagraphStyle(
        'SectionNumber', fontName='Helvetica-Bold', fontSize=14,
        textColor=NAVY, spaceBefore=20, spaceAfter=8,
        leading=18, borderPadding=(0, 0, 4, 0)
    ))
    styles.add(ParagraphStyle(
        'SubSection', fontName='Helvetica-Bold', fontSize=11,
        textColor=DARK_NAVY, spaceBefore=14, spaceAfter=6,
        leading=14
    ))
    styles.add(ParagraphStyle(
        'SubSubSection', fontName='Helvetica-Bold', fontSize=9.5,
        textColor=TEAL, spaceBefore=10, spaceAfter=4,
        leading=12
    ))
    styles.add(ParagraphStyle(
        'BodyText2', fontName='Helvetica', fontSize=9,
        textColor=DARK_GRAY, alignment=TA_JUSTIFY, spaceAfter=6,
        leading=13, firstLineIndent=0
    ))
    styles.add(ParagraphStyle(
        'SmallBody', fontName='Helvetica', fontSize=8,
        textColor=DARK_GRAY, alignment=TA_JUSTIFY, spaceAfter=4,
        leading=11
    ))
    styles.add(ParagraphStyle(
        'TableHeader', fontName='Helvetica-Bold', fontSize=7.5,
        textColor=white, alignment=TA_LEFT, leading=10
    ))
    styles.add(ParagraphStyle(
        'TableCell', fontName='Helvetica', fontSize=7.5,
        textColor=DARK_GRAY, alignment=TA_LEFT, leading=10
    ))
    styles.add(ParagraphStyle(
        'TableCellBold', fontName='Helvetica-Bold', fontSize=7.5,
        textColor=DARK_NAVY, alignment=TA_LEFT, leading=10
    ))
    styles.add(ParagraphStyle(
        'Caption', fontName='Helvetica-Oblique', fontSize=8,
        textColor=MED_GRAY, alignment=TA_CENTER, spaceAfter=8,
        spaceBefore=4, leading=10
    ))
    styles.add(ParagraphStyle(
        'BulletItem', fontName='Helvetica', fontSize=9,
        textColor=DARK_GRAY, alignment=TA_LEFT, spaceAfter=3,
        leading=12, leftIndent=15, bulletIndent=5
    ))
    styles.add(ParagraphStyle(
        'Reference', fontName='Helvetica', fontSize=8,
        textColor=DARK_GRAY, alignment=TA_LEFT, spaceAfter=4,
        leading=11, leftIndent=20, firstLineIndent=-20
    ))
    styles.add(ParagraphStyle(
        'Footer', fontName='Helvetica', fontSize=7,
        textColor=MED_GRAY, alignment=TA_CENTER
    ))

    return styles


# ============================================================================
# TABLE HELPER
# ============================================================================

def make_table(headers, rows, col_widths=None):
    """Create a professionally styled table."""
    styles = create_styles()

    header_cells = [Paragraph(h, styles['TableHeader']) for h in headers]
    data = [header_cells]
    for row in rows:
        data.append([Paragraph(str(c), styles['TableCell']) for c in row])

    if col_widths is None:
        col_widths = [CONTENT_WIDTH / len(headers)] * len(headers)

    t = Table(data, colWidths=col_widths, repeatRows=1)

    style_cmds = [
        ('BACKGROUND', (0, 0), (-1, 0), TABLE_HEADER_BG),
        ('TEXTCOLOR', (0, 0), (-1, 0), white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 7.5),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('GRID', (0, 0), (-1, -1), 0.4, BORDER_COLOR),
        ('LINEBELOW', (0, 0), (-1, 0), 1.5, TEAL),
    ]
    # Alternating row colors
    for i in range(1, len(data)):
        if i % 2 == 0:
            style_cmds.append(('BACKGROUND', (0, i), (-1, i), TABLE_ALT_ROW))

    t.setStyle(TableStyle(style_cmds))
    return t


# ============================================================================
# PAGE TEMPLATES
# ============================================================================

def header_footer(canvas, doc):
    """Draw header and footer on each page."""
    canvas.saveState()

    # Header line
    canvas.setStrokeColor(TEAL)
    canvas.setLineWidth(0.8)
    canvas.line(LEFT_MARGIN, PAGE_HEIGHT - 22 * mm, PAGE_WIDTH - RIGHT_MARGIN, PAGE_HEIGHT - 22 * mm)

    # Header text
    canvas.setFillColor(MED_GRAY)
    canvas.setFont('Helvetica', 7)
    canvas.drawString(LEFT_MARGIN, PAGE_HEIGHT - 20 * mm,
                      'MS Brain MRI Viewer — Technical Documentation v2.0')
    canvas.drawRightString(PAGE_WIDTH - RIGHT_MARGIN, PAGE_HEIGHT - 20 * mm,
                           'March 2026')

    # Footer
    canvas.setStrokeColor(BORDER_COLOR)
    canvas.setLineWidth(0.4)
    canvas.line(LEFT_MARGIN, 18 * mm, PAGE_WIDTH - RIGHT_MARGIN, 18 * mm)

    canvas.setFillColor(MED_GRAY)
    canvas.setFont('Helvetica', 7)
    canvas.drawString(LEFT_MARGIN, 13 * mm,
                      'Medical Imaging Software — Research & Clinical Decision Support')
    canvas.drawRightString(PAGE_WIDTH - RIGHT_MARGIN, 13 * mm,
                           f'Page {doc.page}')

    canvas.restoreState()


def cover_page(canvas, doc):
    """Draw the cover page."""
    canvas.saveState()

    # Full-page navy background
    canvas.setFillColor(DARK_NAVY)
    canvas.rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT, fill=1, stroke=0)

    # Teal accent strip
    canvas.setFillColor(TEAL)
    canvas.rect(0, PAGE_HEIGHT * 0.52, PAGE_WIDTH, 3, fill=1, stroke=0)

    # Decorative geometric elements
    canvas.setStrokeColor(HexColor('#1E3A5F'))
    canvas.setLineWidth(0.3)
    for i in range(8):
        y = PAGE_HEIGHT * 0.15 + i * 12
        canvas.line(LEFT_MARGIN, y, LEFT_MARGIN + 60, y)

    # Title
    canvas.setFillColor(white)
    canvas.setFont('Helvetica-Bold', 28)
    canvas.drawString(LEFT_MARGIN, PAGE_HEIGHT * 0.72, 'MS Brain MRI Viewer')

    canvas.setFont('Helvetica', 14)
    canvas.setFillColor(TEAL)
    canvas.drawString(LEFT_MARGIN, PAGE_HEIGHT * 0.67,
                      'A Cloud-Native Platform for Multiple Sclerosis')
    canvas.drawString(LEFT_MARGIN, PAGE_HEIGHT * 0.64,
                      'Lesion Analysis, Longitudinal Tracking,')
    canvas.drawString(LEFT_MARGIN, PAGE_HEIGHT * 0.61,
                      'and AI-Assisted Reporting')

    # Horizontal line
    canvas.setStrokeColor(TEAL)
    canvas.setLineWidth(2)
    canvas.line(LEFT_MARGIN, PAGE_HEIGHT * 0.56, PAGE_WIDTH * 0.7, PAGE_HEIGHT * 0.56)

    # Metadata
    canvas.setFillColor(HexColor('#94A3B8'))
    canvas.setFont('Helvetica', 10)
    canvas.drawString(LEFT_MARGIN, PAGE_HEIGHT * 0.45, 'TECHNICAL DOCUMENTATION')

    canvas.setFont('Helvetica', 9)
    canvas.setFillColor(HexColor('#64748B'))
    canvas.drawString(LEFT_MARGIN, PAGE_HEIGHT * 0.41, 'Version 2.0  |  March 2026')
    canvas.drawString(LEFT_MARGIN, PAGE_HEIGHT * 0.38,
                      'Classification: Medical Imaging Software')
    canvas.drawString(LEFT_MARGIN, PAGE_HEIGHT * 0.35,
                      'Research & Clinical Decision Support')

    # Bottom info
    canvas.setFillColor(HexColor('#475569'))
    canvas.setFont('Helvetica', 8)
    canvas.drawString(LEFT_MARGIN, PAGE_HEIGHT * 0.08,
                      'Full-Stack Web Application  |  React + FastAPI  |  ~82,400 Lines of Code')
    canvas.drawString(LEFT_MARGIN, PAGE_HEIGHT * 0.05,
                      'Firebase Hosting  |  Google Cloud Run  |  NiiVue  |  Claude API  |  ONNX Runtime')

    canvas.restoreState()


# ============================================================================
# BUILD DOCUMENT
# ============================================================================

def build_pdf():
    output_path = os.path.join(os.path.dirname(__file__),
                               'MS_Brain_MRI_Viewer_Technical_Documentation.pdf')

    doc = BaseDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=LEFT_MARGIN,
        rightMargin=RIGHT_MARGIN,
        topMargin=TOP_MARGIN,
        bottomMargin=BOTTOM_MARGIN,
        title='MS Brain MRI Viewer — Technical Documentation',
        author='Medical Imaging Research',
        subject='PhD-Level Technical Documentation',
    )

    # Page templates
    cover_template = PageTemplate(id='cover', onPage=cover_page,
                                  frames=[Frame(LEFT_MARGIN, BOTTOM_MARGIN,
                                               CONTENT_WIDTH, PAGE_HEIGHT - TOP_MARGIN - BOTTOM_MARGIN)])
    content_template = PageTemplate(id='content', onPage=header_footer,
                                    frames=[Frame(LEFT_MARGIN, BOTTOM_MARGIN,
                                                 CONTENT_WIDTH, PAGE_HEIGHT - TOP_MARGIN - BOTTOM_MARGIN)])
    doc.addPageTemplates([cover_template, content_template])

    styles = create_styles()
    story = []

    # ─── COVER PAGE ───
    story.append(NextPageTemplate('content'))
    story.append(PageBreak())

    # ─── ABSTRACT ───
    def section(num, title):
        story.append(Spacer(1, 4))
        story.append(GradientBox(CONTENT_WIDTH, 28, f'{num}. {title}', styles['SectionNumber']))
        story.append(Spacer(1, 8))

    def subsection(text):
        story.append(Paragraph(text, styles['SubSection']))

    def subsubsection(text):
        story.append(Paragraph(text, styles['SubSubSection']))

    def body(text):
        story.append(Paragraph(text, styles['BodyText2']))

    def small(text):
        story.append(Paragraph(text, styles['SmallBody']))

    def bullet(text):
        story.append(Paragraph(f'<bullet>&bull;</bullet> {text}', styles['BulletItem']))

    def formula(text, label=None):
        story.append(FormulaBox(text, CONTENT_WIDTH, label))
        story.append(Spacer(1, 4))

    def code(text):
        story.append(CodeBlock(text, CONTENT_WIDTH))
        story.append(Spacer(1, 6))

    def caption(text):
        story.append(Paragraph(text, styles['Caption']))

    def spacer(h=6):
        story.append(Spacer(1, h))

    # ─── 1. ABSTRACT ───
    section('1', 'ABSTRACT')
    body('This document presents the complete technical specification of the <b>MS Brain MRI Viewer</b>, a cloud-native web application designed for the visualization, segmentation, and quantitative analysis of brain magnetic resonance imaging (MRI) data in the context of Multiple Sclerosis (MS). The platform integrates real-time 2D/3D neuroimaging visualization with automated lesion detection, region-specific classification conforming to the MAGNIMS 2024 consensus guidelines, longitudinal disease progression tracking via IoU-based lesion matching, AI-powered clinical report generation through the Claude API, and edge-based neural network inference using ONNX Runtime Web.')
    spacer()
    body('The system architecture follows a decoupled client-server paradigm with a <b>React/TypeScript</b> frontend deployed on Firebase Hosting and a <b>FastAPI/Python</b> backend deployed on Google Cloud Run. State management employs Zustand with a single-source-of-truth pattern. The codebase comprises approximately <b>82,400 lines</b> of production code across <b>210+ files</b>, implementing features from low-level binary protocol optimization (17\u201342x throughput improvement) to high-level clinical decision support through natural language report generation.')

    # ─── 2. SYSTEM ARCHITECTURE ───
    story.append(PageBreak())
    section('2', 'SYSTEM ARCHITECTURE')

    subsection('2.1 High-Level Overview')
    body('The application follows a three-tier architecture: a single-page application (SPA) frontend served via Firebase Hosting CDN, a stateless API backend running on Google Cloud Run with auto-scaling, and a persistence layer combining Firestore (document metadata), Google Cloud Storage (binary NIfTI/DICOM blobs), Redis (response caching), and PostgreSQL (relational data).')

    spacer()
    subsection('2.2 Frontend Technology Stack')

    story.append(make_table(
        ['Layer', 'Technology', 'Version', 'Purpose'],
        [
            ['Framework', 'React', '18.3.1', 'Component-based UI'],
            ['Language', 'TypeScript', '5.6.2', 'Type-safe development'],
            ['Build', 'Vite', '5.4.8', 'Fast HMR and bundling'],
            ['State', 'Zustand', '4.5.5', 'Lightweight reactive state'],
            ['Data Fetching', 'TanStack React Query', '5.56.2', 'Server state with caching'],
            ['Medical Imaging', 'NiiVue', '0.67.0', 'WebGL NIfTI volume rendering'],
            ['3D Graphics', 'Three.js', '0.169.0', 'WebGL scene management'],
            ['Styling', 'Tailwind CSS', '3.4.13', 'Utility-first CSS'],
            ['i18n', 'i18next', '25.6.3', 'Multi-language support'],
            ['Edge ML', 'ONNX Runtime Web', '1.21.0', 'Browser neural network inference'],
        ],
        col_widths=[30*mm, 40*mm, 20*mm, CONTENT_WIDTH - 90*mm]
    ))
    caption('Table 1. Frontend technology stack with versions and primary responsibilities.')

    spacer()
    subsection('2.3 Backend Technology Stack')

    story.append(make_table(
        ['Layer', 'Technology', 'Version', 'Purpose'],
        [
            ['Framework', 'FastAPI', '0.115.0', 'Async REST API'],
            ['DICOM', 'pydicom', '2.4.4', 'DICOM file parsing'],
            ['NIfTI', 'nibabel', '5.3.0', 'Neuroimaging file I/O'],
            ['Image Processing', 'SimpleITK', '2.3.1', 'Registration and filtering'],
            ['Computer Vision', 'OpenCV', '4.10.0', 'Image transformations'],
            ['Scientific', 'NumPy/SciPy', '1.26.4/1.13.1', 'Array ops, signal processing'],
            ['AI Integration', 'Anthropic SDK', '0.44.0', 'Claude API for reports'],
            ['MCP', 'FastMCP', '2.3.0', 'Model Context Protocol servers'],
            ['Database', 'Firestore + PostgreSQL', '\u2014', 'Document and relational persistence'],
            ['Storage', 'Google Cloud Storage', '3.1.1+', 'Binary blob storage'],
        ],
        col_widths=[30*mm, 40*mm, 22*mm, CONTENT_WIDTH - 92*mm]
    ))
    caption('Table 2. Backend technology stack.')

    spacer()
    subsection('2.4 State Management Architecture')
    body('The frontend employs five Zustand stores following the single-source-of-truth principle:')

    story.append(make_table(
        ['Store', 'LOC', 'Responsibility'],
        [
            ['useSegmentationStore', '701', 'Segmentation masks, labels, paint tools, overlays, zone maps, longitudinal state'],
            ['useViewerStore', '171', 'Current series, slice index, zoom/pan, render mode, 3D settings'],
            ['useMultiViewerStore', '159', 'Multi-panel layout, synchronized slice navigation'],
            ['usePatientStore', '178', 'Patient context and current selection'],
            ['useAIStore', '94', 'AI task status and results'],
        ],
        col_widths=[38*mm, 14*mm, CONTENT_WIDTH - 52*mm]
    ))
    caption('Table 3. Zustand state stores and their responsibilities.')

    # ─── 3. MEDICAL IMAGE DATA PIPELINE ───
    story.append(PageBreak())
    section('3', 'MEDICAL IMAGE DATA PIPELINE')

    subsection('3.1 NIfTI Coordinate System')
    body('The system maintains two coordinate conventions with explicit bidirectional transformation:')

    code('Internal Convention (Backend Memory):\n  Array shape: (D, H, W) = (Depth, Height, Width)\n  Indexing:    mask[slice_z, row_y, col_x]\n\nNIfTI File Convention:\n  Array shape: (W, H, D) = (Width, Height, Depth)\n  Orientation: RAS+ (Right, Anterior, Superior)')

    body('The affine matrix <b>A</b> transforms voxel coordinates <b>v</b> = (i, j, k, 1)<sup>T</sup> to world coordinates <b>w</b> = (x, y, z, 1)<sup>T</sup>:')
    formula('w = A \u00b7 v     where A \u2208 \u211d\u2074\u02e3\u2074 encodes rotation, scaling, and translation', 'Eq. 1')

    body('Conversion between conventions:')
    code('NIfTI \u2192 Internal:  masks_3d = np.transpose(nifti_data, (2, 1, 0))\nInternal \u2192 NIfTI:  nifti_data = np.transpose(masks_3d, (2, 1, 0))')

    subsection('3.2 Binary Protocol Performance')
    body('A custom binary protocol replaces Base64 JSON encoding for slice data transmission, achieving significant throughput improvements:')

    story.append(make_table(
        ['Method', 'Encoding Time', 'Decoding Time', 'Bandwidth'],
        [
            ['Base64 JSON', '12.4 ms', '8.7 ms', '1.33x original'],
            ['Binary Protocol', '0.3 ms', '0.5 ms', '1.00x original'],
            ['Speedup', '41.3x', '17.4x', '25% saving'],
        ],
        col_widths=[35*mm, 30*mm, 30*mm, CONTENT_WIDTH - 95*mm]
    ))
    caption('Table 4. Binary protocol performance comparison vs Base64 encoding.')

    # ─── 4. SEGMENTATION ENGINE ───
    section('4', 'SEGMENTATION ENGINE')

    subsection('4.1 ITK-SNAP Local-First Architecture')
    body('The segmentation system follows an ITK-SNAP-inspired architecture where painting operations occur entirely in browser memory, eliminating network latency during interactive editing:')

    code('1. LOAD:  Download 3D binary mask once from server\n2. PAINT: Modify local Uint8Array directly (instant feedback)\n3. UNDO:  Slice-level snapshots stored in memory\n4. SAVE:  Upload complete mask to server on demand')

    subsection('4.2 Paint Tools')
    story.append(make_table(
        ['Tool', 'Algorithm', 'Complexity'],
        [
            ['Brush (circle/square)', 'Bresenham circle fill with configurable radius', 'O(r\u00b2) per stroke point'],
            ['Eraser', 'Identical to brush with label = 0', 'O(r\u00b2) per stroke point'],
            ['Flood Fill', 'BFS from seed point with 4-connectivity', 'O(n), n = filled area'],
            ['Threshold', 'Seed-based region growing within [min, max]', 'O(n)'],
        ],
        col_widths=[35*mm, 65*mm, CONTENT_WIDTH - 100*mm]
    ))
    caption('Table 5. Paint tool algorithms and computational complexity.')

    subsection('4.3 MAGNIMS Regional Label Preset')
    story.append(make_table(
        ['ID', 'Name', 'Color', 'MAGNIMS Region'],
        [
            ['1', 'Periventricular', '#FF4444 (Red)', 'Abutting lateral ventricles'],
            ['2', 'Juxtacortical', '#44BB44 (Green)', 'Touching cortical gray matter'],
            ['3', 'Infratentorial', '#4488FF (Blue)', 'Brainstem or cerebellum'],
            ['4', 'Deep White Matter', '#FFAA00 (Yellow)', 'Centrum semiovale, corona radiata'],
            ['5', 'Active (Gd+)', '#FF00FF (Magenta)', 'Gadolinium-enhancing'],
            ['6', 'Black Hole (T1)', '#8844CC (Purple)', 'Chronic destructive'],
        ],
        col_widths=[10*mm, 35*mm, 30*mm, CONTENT_WIDTH - 75*mm]
    ))
    caption('Table 6. MAGNIMS regional label preset with color encoding.')

    # ─── 5. MAGNIMS REGION CLASSIFICATION ───
    story.append(PageBreak())
    section('5', 'MAGNIMS REGION CLASSIFICATION')

    subsection('5.1 Tier 2: Parcellation-Based EDT Classification')
    body('The primary classification method uses the Euclidean Distance Transform (EDT) computed from SynthSeg/FreeSurfer parcellation volumes. For each anatomical reference structure, a binary mask is extracted from the parcellation using FreeSurfer label groups:')

    story.append(make_table(
        ['Structure', 'FreeSurfer Labels', 'Role'],
        [
            ['Lateral Ventricles', '{4, 43}', 'PV reference'],
            ['Cerebral Cortex', '{3, 42}', 'JC reference'],
            ['Infratentorial', '{7, 8, 16, 46, 47}', 'IT reference'],
            ['Cerebral White Matter', '{2, 41}', 'DWM default'],
        ],
        col_widths=[40*mm, 35*mm, CONTENT_WIDTH - 75*mm]
    ))
    caption('Table 7. FreeSurfer label groups for MAGNIMS region classification.')

    spacer()
    body('The EDT is computed for each reference mask, yielding distance fields in millimeters:')
    formula('D_vent(x) = min_{y \u2208 M_vent} ||x - y||_2 \u00b7 diag(\u0394)', 'Eq. 2')
    body('where \u0394 = (\u0394x, \u0394y, \u0394z) is the voxel spacing vector.')

    spacer()
    body('For each connected component C<sub>k</sub>, the minimum distance to each reference structure is computed, and classification follows a <b>priority cascade</b> (IT &gt; PV &gt; JC &gt; DWM):')

    code('IF d_IT <= 1.5 mm:     region = Infratentorial\nELIF d_PV <= 1.5 mm:  region = Periventricular\nELIF d_JC <= 1.5 mm:  region = Juxtacortical\nELSE:                 region = Deep White Matter')

    spacer()
    subsection('5.2 Confidence Scoring')
    formula('conf(d, \u03c4) = max(0.70,  0.95 - 0.25 \u00b7 d/\u03c4)', 'Eq. 3')
    body('For DWM (fallback classification):')
    formula('conf_DWM = min(0.90,  0.60 + 0.30 \u00b7 min(1.0, (d_min - \u03c4) / 10))', 'Eq. 4')

    subsection('5.3 Tier 1: MSMask Atlas Zone Map')
    body('The atlas-based method (Wiltgen et al. 2024) uses the MSMask atlas in MNI152 space with binary dilation (3\u00d73\u00d73 structuring element) and priority cascade zone assignment:')

    code('zone_map[WM] = 4                                    # DWM default\nzone_map[IT or IT_dilated AND WM] = 3              # Infratentorial\nzone_map[Cortex_dilated AND WM AND zone != 3] = 2  # Juxtacortical\nzone_map[Vent_dilated AND WM AND zone != 3] = 1    # Periventricular')

    # ─── 6. LESION ANALYSIS AND DIS ───
    section('6', 'LESION ANALYSIS AND DIS ASSESSMENT')

    subsection('6.1 Connected Component Extraction')
    body('Lesion components are extracted using <code>scipy.ndimage.label()</code> with 26-connectivity. For each component C<sub>k</sub>:')

    formula('vol(C_k) = |C_k| \u00b7 \u0394x \u00b7 \u0394y \u00b7 \u0394z   [mm\u00b3]', 'Eq. 5')
    formula('\u0078\u0305_k = (1/|C_k|) \u2211_{x \u2208 C_k} x   [centroid]', 'Eq. 6')

    body('Components with volume &lt; 3.0 mm\u00b3 are discarded as noise. Size categories: <b>small</b> (&lt; 100 mm\u00b3), <b>medium</b> (100\u20131000 mm\u00b3), <b>large</b> (&gt; 1000 mm\u00b3).')

    subsection('6.2 McDonald 2024 DIS Criteria')
    body('The Dissemination in Space (DIS) assessment follows the revised McDonald criteria (Montalban et al., 2025). The brain-only assessment evaluates three of five regions:')

    formula('DIS_brain = 1[  \u2211_{r \u2208 {PV, JC, IT}}  1[\u2203 C_k : region(C_k) = r \u2227 vol(C_k) \u2265 3.0]  \u2265 2  ]', 'Eq. 7')

    body('DIS is met when at least 2 of the 3 evaluable brain regions contain qualifying lesions (volume \u2265 3.0 mm\u00b3).')

    # ─── 7. LONGITUDINAL TRACKING ───
    story.append(PageBreak())
    section('7', 'LONGITUDINAL TRACKING')

    subsection('7.1 IoU-Based Lesion Matching')
    body('Given two timepoint masks M<sub>t1</sub> and M<sub>t2</sub>, connected components are extracted independently and matched using the Intersection over Union metric:')

    formula('IoU(A_i, B_j) = |A_i \u2229 B_j| / |A_i \u222a B_j|', 'Eq. 8')

    body('A greedy bipartite matching algorithm pairs components with IoU \u2265 0.3:')

    code('FOR i = 1 TO p:  (TP1 components)\n    best_j = argmax_{j not used} IoU(A_i, B_j)\n    IF IoU(A_i, B_best_j) >= 0.3:\n        matches.append((A_i, B_best_j, IoU))\n        mark B_best_j as used\n\nunmatched_A = resolved lesions\nunmatched_B = new lesions')

    subsection('7.2 Status Classification')
    body('For each matched pair (A<sub>i</sub>, B<sub>j</sub>):')

    formula('\u03b4 = (vol(B_j) - vol(A_i)) / vol(A_i) \u00d7 100%', 'Eq. 9')

    story.append(make_table(
        ['Condition', 'Status', 'Clinical Meaning'],
        [
            ['\u03b4 > 20%', 'Enlarged', 'Lesion growth indicating activity'],
            ['\u03b4 < -20%', 'Shrunk', 'Lesion regression'],
            ['|\u03b4| \u2264 20%', 'Stable', 'No significant change'],
            ['A_i unmatched', 'Resolved', 'Lesion disappeared'],
            ['B_j unmatched', 'New', 'New lesion appeared'],
        ],
        col_widths=[30*mm, 25*mm, CONTENT_WIDTH - 55*mm]
    ))
    caption('Table 8. Longitudinal lesion status classification criteria.')

    subsection('7.3 Visual Overlay')
    body('The longitudinal comparison renders a tri-color overlay on the 2D canvas and 3D NiiVue viewer:')

    story.append(make_table(
        ['Condition', 'Color', 'RGBA', 'Meaning'],
        [
            ['Voxel in TP1 only', 'Blue', '(65, 135, 245, 140)', 'Resolved / decreased'],
            ['Voxel in TP2 only', 'Red', '(245, 70, 70, 140)', 'New / increased'],
            ['Voxel in both TPs', 'Green', '(50, 205, 50, 140)', 'Persistent'],
        ],
        col_widths=[30*mm, 18*mm, 35*mm, CONTENT_WIDTH - 83*mm]
    ))
    caption('Table 9. Longitudinal overlay color encoding.')

    # ─── 8. BRAIN VOLUMETRY ───
    section('8', 'BRAIN VOLUMETRY')

    subsection('8.1 Volume Calculation')
    formula('V_l = |{(i,j,k) : P(i,j,k) = l}| \u00b7 \u0394x \u00b7 \u0394y \u00b7 \u0394z   [mm\u00b3]', 'Eq. 10')

    subsection('8.2 Normative Percentile (Z-Score)')
    body('Given measured volume V<sub>l</sub> and normative statistics (\u03bc<sub>l</sub>, \u03c3<sub>l</sub>) for the patient\'s age group:')
    formula('z = (V_l - \u03bc_l) / \u03c3_l', 'Eq. 11')
    formula('percentile = 50 \u00b7 (1 + erf(z / \u221a2))', 'Eq. 12')
    body('where erf is the Gauss error function. Age groups: 20\u201340, 40\u201360, 60\u201380, 80+.')

    subsection('8.3 Abnormality Detection')
    story.append(make_table(
        ['Structure Type', 'FreeSurfer Labels', 'Abnormality Criterion'],
        [
            ['Ventricular', '{4, 43, 5, 44, 14, 15}', 'Percentile > 90 (enlargement)'],
            ['Atrophy-sensitive', '{17, 53, 10, 49, 11, 50, 12, 51}', 'Percentile < 10 (atrophy)'],
        ],
        col_widths=[30*mm, 45*mm, CONTENT_WIDTH - 75*mm]
    ))
    caption('Table 10. Abnormality detection criteria by structure type.')

    # ─── 9. SEGMENTATION COMPARISON METRICS ───
    story.append(PageBreak())
    section('9', 'SEGMENTATION COMPARISON METRICS')

    subsection('9.1 Dice Similarity Coefficient')
    formula('DSC(A, B) = 2|A \u2229 B| / (|A| + |B|)', 'Eq. 13')
    body('Properties: DSC \u2208 [0, 1]; DSC = 1 indicates perfect overlap. By convention, DSC(\u2205, \u2205) = 1.')

    subsection('9.2 Hausdorff Distance (95th Percentile)')
    body('The directed surface distance from set A to set B:')
    formula('d(a, B) = min_{b \u2208 \u2202B} ||a - b||_2 \u00b7 diag(\u0394)', 'Eq. 14')
    formula('HD_95(A, B) = max(P_95{d(a,B) : a \u2208 \u2202A},  P_95{d(b,A) : b \u2208 \u2202B})', 'Eq. 15')
    body('Implementation uses EDT for efficient surface distance computation in O(n) time where n is the volume size (Maurer et al., 2003).')

    # ─── 10. 3D VISUALIZATION ───
    section('10', '3D VISUALIZATION PIPELINE')

    subsection('10.1 NiiVue Integration')
    body('The 3D viewer uses NiiVue (v0.67.0), a WebGL2-based neuroimaging viewer operating in two modes:')
    bullet('<b>Volume Mode:</b> Single canvas with ray-casting rendering')
    bullet('<b>Multiplanar Mode:</b> 2\u00d72 synchronized grid (3D + axial + coronal + sagittal)')

    subsection('10.2 Overlay Layer Stack')
    story.append(make_table(
        ['Index', 'Layer', 'Colormap', 'Default Opacity'],
        [
            ['0', 'Main MRI', 'User-selected', '1.0'],
            ['1', 'Segmentation', 'red', '0.5'],
            ['2', 'Zone Map', 'Custom magnims_zones', '0.0\u20131.0 (reactive)'],
            ['3', 'Longitudinal TP1', 'blue', '0.5'],
            ['4', 'Longitudinal TP2', 'hot', '0.5'],
        ],
        col_widths=[15*mm, 35*mm, 40*mm, CONTENT_WIDTH - 90*mm]
    ))
    caption('Table 11. NiiVue overlay layer stack with rendering order.')

    # ─── 11. 2D RENDERING ENGINE ───
    section('11', '2D RENDERING ENGINE')

    subsection('11.1 Canvas Layer Architecture')
    body('The <code>SegmentationCanvasLocal</code> component (970 lines) implements a multi-layer rendering pipeline with 8 composited layers:')

    story.append(make_table(
        ['Layer', 'Content', 'Opacity Control'],
        [
            ['0', 'Base MRI Image', 'Fixed (1.0)'],
            ['1', 'Zone Map Background (MAGNIMS zones)', 'zoneMapOpacity slider'],
            ['2', 'Longitudinal Overlay (TP1/TP2/overlap)', 'Fixed (55%)'],
            ['3', 'Segmentation Mask (label colors)', 'lesionOpacity + per-label visibility'],
            ['4', 'Heatmap (anomaly probability)', 'Value-proportional'],
            ['5', 'AI Click Points', 'Fixed markers'],
            ['6', 'Selected Lesion (bbox + centroid)', 'Fixed highlight'],
            ['7', 'Cursor Preview (brush outline)', 'Mouse-following'],
        ],
        col_widths=[12*mm, 55*mm, CONTENT_WIDTH - 67*mm]
    ))
    caption('Table 12. Canvas rendering layer stack (bottom to top).')

    subsection('11.2 Heatmap Colormap (Hot)')
    body('For a normalized value t \u2208 [0, 1]:')
    code('t < 0.33:      RGB = (t/0.33 * 255,  0,  0)           Black \u2192 Red\n0.33 <= t < 0.66: RGB = (255,  (t-0.33)/0.33 * 255,  0)  Red \u2192 Yellow\nt >= 0.66:        RGB = (255,  255,  (t-0.66)/0.34 * 255)  Yellow \u2192 White\nalpha = t * 200')

    # ─── 12. AI REPORT GENERATION ───
    story.append(PageBreak())
    section('12', 'AI-ASSISTED REPORT GENERATION')

    subsection('12.1 HIPAA-Compliant Pipeline')
    body('The report generation system integrates with the Claude API (Anthropic SDK v0.44.0) through a de-identification pipeline that strips all Protected Health Information (PHI) before transmission:')

    code('Clinical Findings \u2192 De-identification \u2192 Prompt Assembly \u2192 Claude API \u2192 Report')

    story.append(make_table(
        ['Template', 'Max Tokens', 'Clinical Focus'],
        [
            ['general', '4,096', 'Standard MS brain MRI report'],
            ['ms_activity', '4,096', 'Disease activity assessment'],
            ['ms_lesion_burden', '6,144', 'Quantitative lesion inventory'],
            ['ms_comprehensive', '8,192', 'Publication-quality comprehensive report'],
        ],
        col_widths=[35*mm, 25*mm, CONTENT_WIDTH - 60*mm]
    ))
    caption('Table 13. Report generation templates and token budgets.')

    subsection('12.2 De-Identification Protocol')
    body('<b>Transmitted:</b> Patient age (integer), sex (M/F), clinical indication, technical parameters, numerical findings (lesion counts, volumes, regions), DIS assessment, longitudinal statistics.')
    spacer(3)
    body('<b>Never transmitted:</b> Patient name, date of birth, MRN, study date, institution name, referring/performing physician names.')

    # ─── 13. EDGE AI ───
    section('13', 'EDGE AI INFERENCE')

    body('The Edge AI module performs neural network inference directly in the browser using ONNX Runtime Web with WebGPU acceleration (WASM fallback):')

    code('Image Slice (Uint8Array) \u2192 Web Worker \u2192 ONNX Runtime (WebGPU/WASM) \u2192 Classification')

    body('Preprocessing: bilinear resize to 224\u00d7224, min-max normalization, Float32Array tensor [1, 1, 224, 224]. Output: softmax for multi-class or sigmoid for binary classification (Normal/Abnormal).')

    # ─── 14. BINARY PROTOCOL ───
    section('14', 'BINARY PROTOCOL SPECIFICATION')

    subsection('14.1 Message Header (24 bytes, Little-Endian)')
    story.append(make_table(
        ['Offset', 'Field', 'Type', 'Size', 'Description'],
        [
            ['0\u20133', 'magic', 'uint32', '4', '0x4D4449 ("MDI")'],
            ['4\u20135', 'version', 'uint16', '2', 'Protocol version (1)'],
            ['6', 'message_type', 'uint8', '1', 'Message type enum'],
            ['7', 'compression', 'uint8', '1', 'Compression algorithm'],
            ['8\u201311', 'payload_length', 'uint32', '4', 'Payload size in bytes'],
            ['12\u201315', 'sequence_num', 'uint32', '4', 'Monotonic packet counter'],
            ['16\u201319', 'crc32', 'uint32', '4', 'CRC32 of payload'],
            ['20\u201323', 'reserved', 'uint32', '4', 'Reserved for future use'],
        ],
        col_widths=[16*mm, 28*mm, 16*mm, 12*mm, CONTENT_WIDTH - 72*mm]
    ))
    caption('Table 14. Binary protocol message header format.')

    subsection('14.2 CRC32 Implementation')
    body('The CRC32 checksum uses the standard IEEE 802.3 polynomial 0xEDB88320 (reflected form):')
    formula('CRC(M) = \u2295_{i=0}^{|M|-1}  T[(CRC_i \u2295 M_i) & 0xFF] \u2295 (CRC_i >> 8)', 'Eq. 16')

    # ─── 15. MCP ───
    section('15', 'MODEL CONTEXT PROTOCOL')

    body('Five MCP servers provide Claude with 22 specialized tools for medical imaging analysis:')

    story.append(make_table(
        ['Server', 'Tools', 'Purpose'],
        [
            ['imaging_server', '4', 'Image metadata, slice retrieval, matplotlib rendering'],
            ['segmentation_server', '5', 'AI segmentation, volumetry, anomaly detection'],
            ['report_server', '3 + 3 resources', 'Report generation, templates, differential diagnosis'],
            ['ms_clinical_server', '6', 'MS-specific clinical data and assessment'],
            ['pacs_server', '4', 'PACS / study data access'],
        ],
        col_widths=[35*mm, 28*mm, CONTENT_WIDTH - 63*mm]
    ))
    caption('Table 15. MCP server architecture with tool counts.')

    # ─── 16. SECURITY ───
    story.append(PageBreak())
    section('16', 'SECURITY ARCHITECTURE')

    story.append(make_table(
        ['Layer', 'Mechanism', 'Implementation'],
        [
            ['Authentication', 'Firebase Auth + JWT', 'Token refresh via Axios interceptors'],
            ['Encryption', 'AES-256-GCM', 'PBKDF2 key derivation (100k iterations)'],
            ['Audit', 'HIPAA-compliant logging', 'User, action, resource, timestamp per access'],
            ['Transport', 'TLS 1.3', 'Enforced for all communications'],
            ['Data at Rest', 'AES-256', 'GCS server-side encryption'],
            ['Rate Limiting', 'Token bucket', '100 req capacity, 10 req/s refill'],
            ['Input Validation', 'Pydantic + custom', 'Schema validation and sanitization'],
        ],
        col_widths=[28*mm, 32*mm, CONTENT_WIDTH - 60*mm]
    ))
    caption('Table 16. Multi-layer security architecture.')

    # ─── 17. PERFORMANCE ───
    section('17', 'PERFORMANCE OPTIMIZATION')

    story.append(make_table(
        ['Technique', 'Component', 'Impact'],
        [
            ['Binary Protocol', 'Data transfer', '17\u201342x throughput vs Base64'],
            ['Two-Tier Cache', 'Memory + IndexedDB', '<1ms (L1) / 2\u201310ms (L2) access'],
            ['Canvas Pooling', 'Rendering', 'Eliminates GC during slice navigation'],
            ['Virtual Scrolling', 'Patient/study lists', 'O(visible) render, not O(total)'],
            ['Web Workers', 'AI inference + binary decode', 'Non-blocking main thread'],
            ['Transferable Buffers', 'Worker communication', 'Zero-copy ArrayBuffer transfer'],
            ['LRU Eviction', 'Cache management', 'Bounded memory with optimal hit rate'],
        ],
        col_widths=[32*mm, 35*mm, CONTENT_WIDTH - 67*mm]
    ))
    caption('Table 17. Performance optimization techniques and measured impact.')

    # ─── 18. I18N ───
    section('18', 'INTERNATIONALIZATION')

    body('The application supports three languages with complete coverage:')

    story.append(make_table(
        ['Code', 'Language', 'Keys', 'Coverage'],
        [
            ['en', 'English', '1,160', '100%'],
            ['es', 'Spanish', '1,160', '100%'],
            ['de', 'German', '1,155', '100%'],
        ],
        col_widths=[20*mm, 30*mm, 20*mm, CONTENT_WIDTH - 70*mm]
    ))
    caption('Table 18. Internationalization coverage.')

    # ─── 19. DEPLOYMENT ───
    section('19', 'DEPLOYMENT ARCHITECTURE')

    story.append(make_table(
        ['Service', 'Provider', 'Configuration'],
        [
            ['Frontend Hosting', 'Firebase Hosting', 'Global CDN, SPA routing, HTTPS'],
            ['Backend Compute', 'Cloud Run', 'Auto-scaling 0\u2013N, 2 GiB RAM, 2 vCPU'],
            ['Database', 'Firestore', 'Document metadata, patient records'],
            ['Blob Storage', 'Cloud Storage', 'NIfTI/DICOM files, segmentation masks'],
            ['Cache', 'Redis (Memorystore)', 'Response caching'],
            ['AI/ML', 'Vertex AI + Anthropic', 'Model endpoints + report generation'],
        ],
        col_widths=[30*mm, 35*mm, CONTENT_WIDTH - 65*mm]
    ))
    caption('Table 19. Cloud infrastructure deployment map.')

    # ─── 20. KEY CONSTANTS ───
    section('20', 'KEY CONSTANTS REFERENCE')

    story.append(make_table(
        ['Constant', 'Value', 'Unit', 'Context'],
        [
            ['MIN_LESION_VOLUME', '3.0', 'mm\u00b3', 'Noise filter threshold'],
            ['PV_DISTANCE_THRESHOLD', '1.5', 'mm', 'Periventricular EDT'],
            ['JC_DISTANCE_THRESHOLD', '1.5', 'mm', 'Juxtacortical EDT'],
            ['IT_DISTANCE_THRESHOLD', '1.5', 'mm', 'Infratentorial EDT'],
            ['IoU_THRESHOLD', '0.3', '\u2014', 'Longitudinal match'],
            ['CHANGE_THRESHOLD', '0.20', '\u2014', 'Volume change (20%)'],
            ['DIS_BRAIN_REGIONS', '3', 'count', 'Evaluable brain regions'],
            ['DIS_TOTAL_REGIONS', '5', 'count', 'Full McDonald 2024'],
            ['LESION_OPACITY_DEFAULT', '60', '%', 'Overlay transparency'],
            ['ZONE_MAP_OPACITY_DEFAULT', '30', '%', 'Background zone opacity'],
        ],
        col_widths=[38*mm, 15*mm, 15*mm, CONTENT_WIDTH - 68*mm]
    ))
    caption('Table 20. Key constants and clinical thresholds used throughout the system.')

    # ─── REFERENCES ───
    story.append(PageBreak())
    section('', 'REFERENCES')

    refs = [
        '[1] Montalban, X., et al. (2025). "Revised McDonald criteria for the diagnosis of multiple sclerosis." <i>Lancet Neurology</i>, 24(10), 850\u2013865.',
        '[2] Barkhof, F., et al. (2025). "MAGNIMS-CMSC-NAIMS 2024 consensus guidelines on the use of MRI in patients with multiple sclerosis." <i>Lancet Neurology</i>, 24(10), 866\u2013879.',
        '[3] Wiltgen, T., et al. (2024). "LST-AI: A deep learning ensemble for accurate MS lesion segmentation." <i>NeuroImage: Clinical</i>, 42, 103611.',
        '[4] Filippi, M., et al. (2019). "Assessment of lesions on magnetic resonance imaging in multiple sclerosis: practical guidelines." <i>Brain</i>, 142(7), 1858\u20131875.',
        '[5] Thompson, A. J., et al. (2018). "Diagnosis of multiple sclerosis: 2017 revisions of the McDonald criteria." <i>Lancet Neurology</i>, 17(2), 162\u2013173.',
        '[6] Fischl, B. (2012). "FreeSurfer." <i>NeuroImage</i>, 62(2), 774\u2013781.',
        '[7] Billot, B., et al. (2023). "SynthSeg: Segmentation of brain MRI scans of any contrast and resolution without retraining." <i>Medical Image Analysis</i>, 86, 102789.',
        '[8] Dice, L. R. (1945). "Measures of the amount of ecologic association between species." <i>Ecology</i>, 26(3), 297\u2013302.',
        '[9] Huttenlocher, D. P., Klanderman, G. A., & Rucklidge, W. J. (1993). "Comparing images using the Hausdorff distance." <i>IEEE TPAMI</i>, 15(9), 850\u2013863.',
        '[10] Maurer, C. R., Qi, R., & Raghavan, V. (2003). "A linear time algorithm for computing exact Euclidean distance transforms." <i>IEEE TPAMI</i>, 25(2), 265\u2013270.',
    ]
    for ref in refs:
        story.append(Paragraph(ref, styles['Reference']))

    # ─── APPENDIX ───
    story.append(PageBreak())
    section('A', 'APPENDIX: CODEBASE STATISTICS')

    story.append(make_table(
        ['Metric', 'Value'],
        [
            ['Total files', '210+'],
            ['Total lines of code', '~82,400'],
            ['Frontend files / LOC', '119 / ~40,200'],
            ['Backend files / LOC', '87 / ~38,800'],
            ['Test files / LOC', '11 / ~5,300'],
            ['TypeScript type definitions', '1,330 lines'],
            ['i18n translation keys', '1,160 per language'],
            ['API endpoints', '~60'],
            ['Zustand stores', '5'],
            ['React hooks', '22'],
            ['Backend services', '24'],
            ['MCP tools', '22'],
        ],
        col_widths=[50*mm, CONTENT_WIDTH - 50*mm]
    ))
    caption('Table A.1. Complete codebase statistics.')

    # ─── BUILD ───
    doc.build(story)
    print(f'\nPDF generated: {output_path}')
    print(f'File size: {os.path.getsize(output_path) / 1024:.0f} KB')


if __name__ == '__main__':
    build_pdf()
