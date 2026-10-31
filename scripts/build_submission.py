"""Render the four-page Markdown explanation; requires optional requirements-docs.txt."""
import argparse
import html
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def markup(text):
    text = html.escape(text)
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    return re.sub(r'`([^`]+)`', r'<font name="Courier" size="8.5">\1</font>', text)


def build(source, destination):
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_LEFT
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except ImportError as error:
        raise ValueError('Install optional requirements-docs.txt to rebuild the PDF.') from error
    pages = source.read_text(encoding='utf-8').split('<!-- pagebreak -->')
    if len(pages) != 4:
        raise ValueError('The submission source must define exactly four pages.')
    destination.parent.mkdir(parents=True, exist_ok=True)
    width, height = A4
    navy, teal = colors.HexColor('#142c41'), colors.HexColor('#087f8c')
    body = ParagraphStyle('Body', fontName='Helvetica', fontSize=10, leading=13.8,
                          spaceAfter=10, alignment=TA_LEFT, textColor=navy)
    heading = ParagraphStyle('Heading', parent=body, fontName='Helvetica-Bold',
                             fontSize=17, leading=21, spaceBefore=3, spaceAfter=17)
    title = ParagraphStyle('Title', parent=heading, fontSize=23, leading=27, spaceAfter=13)
    small = ParagraphStyle('Small', parent=body, fontSize=8.5, leading=11.5, spaceAfter=0)
    doc = SimpleDocTemplate(str(destination), pagesize=A4, leftMargin=46, rightMargin=46,
                            topMargin=55, bottomMargin=45,
                            title='Retail SQL Reconciliation and Evidence-Based Investigation',
                            author='Jiacheng')

    def decorate(canvas, document):
        canvas.setStrokeColor(teal)
        canvas.setLineWidth(1.1)
        canvas.line(46, height - 35, width - 46, height - 35)
        canvas.setFillColor(navy)
        canvas.setFont('Helvetica', 8)
        canvas.drawString(46, height - 27, 'MIRAFLORES AI  /  ENGINEERING CASE STUDY')
        canvas.drawString(46, 25, 'Jiacheng  |  Synthetic retail evidence')
        canvas.drawRightString(width - 46, 25, f'{document.page} / 4')

    story = []
    for page_index, page in enumerate(pages):
        if page_index:
            story.append(PageBreak())
        for block in re.split(r'\n\s*\n', page.strip()):
            if block.startswith('|'):
                rows = [line.strip().strip('|').split('|') for line in block.splitlines()]
                rows = [row for row in rows if not all(re.fullmatch(r'[ :\-]+', cell) for cell in row)]
                cells = [[Paragraph(markup(cell.strip()), small) for cell in row] for row in rows]
                table = Table(cells, colWidths=[94, 275, width - 92 - 369], hAlign='LEFT')
                table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e7f2f3')),
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                    ('LEFTPADDING', (0, 0), (-1, -1), 7),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 7),
                    ('TOPPADDING', (0, 0), (-1, -1), 8),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                    ('LINEBELOW', (0, 0), (-1, 0), .7, teal),
                    ('LINEBELOW', (0, 1), (-1, -1), .3, colors.HexColor('#cbd6df'))]))
                story.extend([table, Spacer(1, 12)])
            elif block.startswith('# '):
                story.append(Paragraph(markup(block[2:]), title))
            elif block.startswith('## '):
                story.append(Paragraph(markup(block[3:]), heading))
            else:
                story.append(Paragraph(markup(' '.join(block.splitlines())), body))
    doc.build(story, onFirstPage=decorate, onLaterPages=decorate)
    if doc.page != 4:
        destination.unlink()
        raise ValueError(f'Submission overflowed to {doc.page} pages; shorten the source before delivery.')
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=ROOT / 'docs/CASE_STUDY.md')
    parser.add_argument('--output', type=Path, default=ROOT / 'output/pdf/CASE_STUDY.pdf')
    args = parser.parse_args()
    try:
        destination = build(args.source, args.output)
    except (OSError, ValueError) as error:
        parser.exit(2, f'PDF ERROR: {error}\n')
    print(f'Written submission: {destination} (4 pages)')


if __name__ == '__main__':
    main()
