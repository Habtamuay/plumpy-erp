from django.http import HttpResponse
from io import BytesIO
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_RIGHT


def generate_invoice_pdf(invoice):
    """
    Generate a PDF for the given invoice and return bytes
    """
    buffer = BytesIO()
    
    # Create the PDF object
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=20*mm,
        leftMargin=20*mm,
        topMargin=20*mm,
        bottomMargin=20*mm
    )
    
    # Container for the 'Flowable' objects
    elements = []
    
    # Get styles
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name='Center',
        alignment=TA_CENTER,
        fontSize=12
    ))
    styles.add(ParagraphStyle(
        name='Right',
        alignment=TA_RIGHT,
        fontSize=10
    ))
    
    # Company Header
    company_name = invoice.company.name if hasattr(invoice, 'company') and invoice.company else "Company Name"
    elements.append(Paragraph(company_name, styles['Heading1']))
    elements.append(Paragraph(f"Invoice #{invoice.invoice_number}", styles['Heading2']))
    elements.append(Spacer(1, 10*mm))
    
    # Invoice Info
    invoice_data = [
        ["Invoice Date:", invoice.invoice_date.strftime('%Y-%m-%d') if invoice.invoice_date else ''],
        ["Due Date:", invoice.due_date.strftime('%Y-%m-%d') if invoice.due_date else ''],
    ]
    
    # Add customer if exists
    if hasattr(invoice, 'customer') and invoice.customer:
        invoice_data.append(["Customer:", invoice.customer.name])
        if hasattr(invoice.customer, 'address') and invoice.customer.address:
            invoice_data.append(["Address:", invoice.customer.address])
    
    invoice_table = Table(invoice_data, colWidths=[50*mm, 100*mm])
    invoice_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    elements.append(invoice_table)
    elements.append(Spacer(1, 10*mm))
    
    # Items Table
    items_data = [['Item', 'Qty', 'Unit', 'Unit Price', 'Total']]
    
    # Check if lines exist
    if hasattr(invoice, 'lines') and invoice.lines.exists():
        for line in invoice.lines.all():
            item_name = line.item.name if hasattr(line, 'item') and line.item else 'Unknown Item'
            if len(item_name) > 30:
                item_name = item_name[:30] + '...'
            
            quantity = str(line.quantity) if hasattr(line, 'quantity') else '0'
            unit = line.unit.abbreviation if hasattr(line, 'unit') and line.unit else ''
            unit_price = f"{line.unit_price:.2f}" if hasattr(line, 'unit_price') else '0.00'
            total = f"{line.total_price:.2f}" if hasattr(line, 'total_price') else '0.00'
            
            items_data.append([
                item_name,
                quantity,
                unit,
                unit_price,
                total
            ])
    else:
        items_data.append(['No items', '', '', '', ''])
    
    items_table = Table(items_data, colWidths=[70*mm, 20*mm, 20*mm, 30*mm, 30*mm])
    items_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    elements.append(items_table)
    elements.append(Spacer(1, 10*mm))
    
    # Get financial values safely
    subtotal = float(invoice.subtotal) if hasattr(invoice, 'subtotal') and invoice.subtotal else 0
    tax_amount = float(invoice.tax_amount) if hasattr(invoice, 'tax_amount') and invoice.tax_amount else 0
    total_amount = float(invoice.total_amount) if hasattr(invoice, 'total_amount') and invoice.total_amount else 0
    
    # Totals
    totals_data = [
        ["Subtotal:", f"{subtotal:.2f}"],
        ["Tax:", f"{tax_amount:.2f}"],
        ["Total:", f"{total_amount:.2f}"],
    ]
    
    totals_table = Table(totals_data, colWidths=[40*mm, 40*mm])
    totals_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('LINEABOVE', (0, -1), (-1, -1), 1, colors.black),
        ('FONTWEIGHT', (0, -1), (-1, -1), 'BOLD'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    elements.append(totals_table)
    
    # Build PDF
    doc.build(elements)
    
    # Get the value of the BytesIO buffer
    pdf = buffer.getvalue()
    buffer.close()
    
    return pdf