from django.http import HttpResponse
from io import BytesIO
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
import os
from django.templatetags.static import static


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
    company_name = invoice.company.name if hasattr(invoice, 'company') and invoice.company else "HILINA ENRICHED FOODS PLC"
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
        if hasattr(invoice.customer, 'tin') and invoice.customer.tin:
            invoice_data.append(["TIN:", invoice.customer.tin])
        if hasattr(invoice.customer, 'address') and invoice.customer.address:
            invoice_data.append(["Address:", invoice.customer.address])
        if hasattr(invoice.customer, 'subcity') and invoice.customer.subcity:
            invoice_data.append(["Subcity:", invoice.customer.subcity])
    
    # Add reference numbers if available
    if hasattr(invoice, 'fs_number') and invoice.fs_number:
        invoice_data.append(["FS No.:", invoice.fs_number])
    if hasattr(invoice, 'reference_number') and invoice.reference_number:
        invoice_data.append(["Ref No.:", invoice.reference_number])
    
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
    items_data = [['No.', 'Code', 'Description', 'Unit', 'Qty', 'Unit Price', 'Total']]
    
    # Check if lines exist
    if hasattr(invoice, 'lines') and invoice.lines.exists():
        for i, line in enumerate(invoice.lines.all(), 1):
            item_name = line.item.name if hasattr(line, 'item') and line.item else 'Unknown Item'
            if len(item_name) > 30:
                item_name = item_name[:30] + '...'
            
            items_data.append([
                str(i),
                line.item.code if hasattr(line, 'item') and line.item and hasattr(line.item, 'code') else '',
                item_name,
                line.unit.abbreviation if hasattr(line, 'unit') and line.unit else '',
                f"{line.quantity:.2f}" if hasattr(line, 'quantity') else '0',
                f"{line.unit_price:.2f}" if hasattr(line, 'unit_price') else '0.00',
                f"{line.total_price:.2f}" if hasattr(line, 'total_price') else '0.00'
            ])
    else:
        items_data.append(['No items', '', '', '', '', '', ''])
    
    items_table = Table(items_data, colWidths=[15*mm, 25*mm, 65*mm, 20*mm, 20*mm, 25*mm, 25*mm])
    items_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('ALIGN', (0, 0), (0, -1), 'CENTER'),
        ('ALIGN', (4, 0), (6, -1), 'RIGHT'),
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
    tax_rate = float(invoice.tax_rate) if hasattr(invoice, 'tax_rate') else 15
    
    # Totals
    totals_data = [
        ["SUBTOTAL:", f"{subtotal:,.2f}"],
        [f"VAT ({tax_rate}%):", f"{tax_amount:,.2f}"],
        ["GRAND TOTAL:", f"{total_amount:,.2f}"],
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
    elements.append(Spacer(1, 10*mm))
    
    # Add payment method and notes
    payment_method = invoice.payment_method if hasattr(invoice, 'payment_method') else ''
    notes = invoice.notes if hasattr(invoice, 'notes') else ''
    
    if payment_method or notes:
        footer_data = []
        if payment_method:
            footer_data.append([f"Payment Method: {payment_method.title() if payment_method else ''}"])
        if notes:
            footer_data.append([f"Notes: {notes}"])
        
        # Add amount in words if num2words is available
        try:
            from num2words import num2words
            words = num2words(total_amount, lang='en').replace(' and', '').title() + ' Birr Only'
            footer_data.append([f"Amount In Words: {words}"])
        except ImportError:
            pass
        
        footer_table = Table(footer_data, colWidths=[150*mm])
        footer_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ]))
        elements.append(footer_table)
    
    # Build PDF
    doc.build(elements)
    
    # Get the value of the BytesIO buffer
    pdf = buffer.getvalue()
    buffer.close()
    
    return pdf


def generate_invoice_pdf_response(invoice):
    """
    Generate PDF and return HttpResponse for download
    """
    pdf = generate_invoice_pdf(invoice)
    
    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="invoice_{invoice.invoice_number}.pdf"'
    
    return response


def generate_invoice_pdf_simple(invoice):
    """
    Generate a simpler PDF for the given invoice using canvas (fallback method)
    """
    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="invoice_{invoice.invoice_number}.pdf"'

    p = canvas.Canvas(response, pagesize=A4)
    y = 800

    # Try to add logo if exists
    try:
        logo_path = static('images/hilina_logo.png')
        logo_file = os.path.join(os.getcwd(), logo_path.lstrip('/'))
        if os.path.exists(logo_file):
            p.drawImage(logo_file, 50, y-60, width=80, preserveAspectRatio=True)
    except Exception:
        pass

    # Company header
    p.setFont("Helvetica-Bold", 16)
    p.drawCentredString(300, y, "HILINA ENRICHED FOODS PLC")
    y -= 20
    p.setFont("Helvetica", 8)
    p.drawCentredString(300, y, "S/CITY OROMIA   KEBELE 01   H NO NEW   TEL 011651 9909")
    y -= 12
    p.drawCentredString(300, y, "TIN 0000620114    VAT 24190")
    y -= 16
    p.setFont("Helvetica-Bold", 12)
    p.drawCentredString(300, y, f"Invoice #{invoice.invoice_number}")
    y -= 30

    # Customer info
    left_x = 50
    p.setFont("Helvetica-Bold", 9)
    p.drawString(left_x, y, "Customer Information")
    y -= 14
    
    p.setFont("Helvetica", 8)
    p.drawString(left_x, y, f"Customer: {invoice.customer.name if invoice.customer else 'N/A'}")
    if hasattr(invoice.customer, 'tin') and invoice.customer.tin:
        p.drawString(left_x+150, y, f"TIN: {invoice.customer.tin}")
    y -= 12
    
    if hasattr(invoice.customer, 'subcity') and invoice.customer.subcity:
        p.drawString(left_x, y, f"Subcity: {invoice.customer.subcity}")
        y -= 12
    
    # Invoice dates
    p.drawString(left_x, y, f"Invoice Date: {invoice.invoice_date}")
    p.drawString(left_x+150, y, f"Due Date: {invoice.due_date}")
    y -= 20
    
    # Table header
    p.setFont("Helvetica-Bold", 9)
    p.drawString(left_x, y, "No")
    p.drawString(left_x+25, y, "Code")
    p.drawString(left_x+80, y, "Description")
    p.drawString(left_x+220, y, "Unit")
    p.drawString(left_x+255, y, "Qty")
    p.drawRightString(left_x+350, y, "Unit Price")
    p.drawRightString(left_x+430, y, "Total")
    y -= 14

    p.setFont("Helvetica", 8)
    line_no = 1
    for line in invoice.lines.all():
        p.drawString(left_x, y, str(line_no))
        p.drawString(left_x+25, y, line.item.code if line.item else "")
        p.drawString(left_x+80, y, line.item.name[:30] + "..." if line.item and len(line.item.name) > 30 else (line.item.name if line.item else ""))
        p.drawString(left_x+220, y, line.unit.abbreviation if line.unit else "")
        p.drawString(left_x+255, y, f"{line.quantity:.2f}")
        p.drawRightString(left_x+350, y, f"{line.unit_price:,.2f}")
        p.drawRightString(left_x+430, y, f"{line.total_price:,.2f}")
        y -= 14
        line_no += 1
        if y < 100:
            p.showPage()
            y = 800
    y -= 20

    # Totals
    tx = left_x + 280
    p.setFont("Helvetica-Bold", 9)
    p.drawString(tx, y, "SUBTOTAL")
    p.drawRightString(left_x+430, y, f"{invoice.subtotal:,.2f}")
    y -= 14
    p.drawString(tx, y, f"VAT({invoice.tax_rate}%)")
    p.drawRightString(left_x+430, y, f"{invoice.tax_amount:,.2f}")
    y -= 14
    p.drawString(tx, y, "GRAND TOTAL")
    p.drawRightString(left_x+430, y, f"{invoice.total_amount:,.2f}")
    y -= 30

    # Footer
    p.setFont("Helvetica", 8)
    p.drawString(left_x, y, f"Payment Method: {invoice.get_payment_method_display() if hasattr(invoice, 'payment_method') else 'N/A'}")
    y -= 12
    
    # Amount in words
    try:
        from num2words import num2words
        words = num2words(invoice.total_amount, lang='en').replace(' and', '').title() + ' Birr Only'
        p.drawString(left_x, y, f"Amount In Words: {words}")
        y -= 12
    except ImportError:
        pass
    
    if invoice.notes:
        p.drawString(left_x, y, f"Notes: {invoice.notes}")

    p.showPage()
    p.save()

    return response