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
<<<<<<< HEAD
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
=======

    response = HttpResponse(content_type="application/pdf")

    response["Content-Disposition"] = f'attachment; filename="invoice_{invoice.invoice_number}.pdf"'

    p = canvas.Canvas(response, pagesize=A4)

    y = 800

    # header: logo + company details centered
    try:
        from django.templatetags.static import static
        logo_path = static('images/hilina_logo.png')
        import os
        logo_file = os.path.join(os.getcwd(), logo_path.lstrip('/'))
        p.drawImage(logo_file, 50, y-60, width=80, preserveAspectRatio=True)
    except Exception:
        pass

    p.setFont("Helvetica-Bold", 16)
    p.drawCentredString(300, y, "HILINA ENRICHED FOODS PLC")
    y -= 20
    p.setFont("Helvetica", 8)
    p.drawCentredString(300, y, "S/CITY OROMIA   KEBELE 01   H NO NEW   TEL 011651 9909")
    y -= 12
    p.drawCentredString(300, y, "TIN 0000620114    VAT 24190")
    y -= 16
    p.setFont("Helvetica-Bold", 12)
    p.drawCentredString(300, y, "CREDIT SALES ATTACHMENT")
    y -= 30

    # customer & reference columns
    left_x = 50
    right_x = 370
    # starting y for both columns
    info_start_y = y
    ref_start_y = y

    p.setFont("Helvetica-Bold", 9)
    p.drawString(left_x, info_start_y, "Customer Info")
    p.drawString(right_x, ref_start_y, "References")
    info_start_y -= 14
    ref_start_y -= 14

    p.setFont("Helvetica", 8)
    p.drawString(left_x, info_start_y, f"Customer: {invoice.customer.name}")
    # show tin next to customer name if available
    if getattr(invoice.customer, 'tin', None):
        p.drawString(left_x+150, info_start_y, f"TIN: {invoice.customer.tin}")
    ref_start_y_val = ref_start_y
    p.drawString(right_x, ref_start_y, f"Date: {invoice.invoice_date}")
    ref_start_y -= 12

    # optional customer fields (trade name, category, subcity)
    if getattr(invoice.customer, 'trade_name', None):
        info_start_y -= 12
        p.drawString(left_x, info_start_y, f"Trade Name: {invoice.customer.trade_name}")
    if getattr(invoice.customer, 'category', None):
        info_start_y -= 12
        p.drawString(left_x, info_start_y, f"Category: {invoice.customer.category}")
    if getattr(invoice.customer, 'subcity', None):
        info_start_y -= 12
        p.drawString(left_x, info_start_y, f"Subcity: {invoice.customer.subcity}")

    # draw FS/ref on right independently
    if getattr(invoice, 'fs_number', None):
        p.drawString(right_x, ref_start_y, f"FS No.: {invoice.fs_number}")
        ref_start_y -= 12
    if getattr(invoice, 'reference_number', None):
        p.drawString(right_x, ref_start_y, f"Ref No.: {invoice.reference_number}")
        ref_start_y -= 12

    # advance master y to lower of both columns
    y = min(info_start_y, ref_start_y) - 20

    # table header
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

    y -= 20

    line_no = 1
    for line in invoice.lines.all():
        p.drawString(left_x, y, str(line_no))
        p.drawString(left_x+25, y, line.item.code or "")
        p.drawString(left_x+80, y, line.item.name)
        p.drawString(left_x+220, y, line.unit.abbreviation if line.unit else "")
        p.drawString(left_x+255, y, str(line.quantity))
        p.drawRightString(left_x+350, y, f"{line.unit_price:,.2f}")
        p.drawRightString(left_x+430, y, f"{line.total_price:,.2f}")
        y -= 14
        line_no += 1
        if y < 100:
            p.showPage()
            y = 800
    y -= 20

    # totals box on right (aligned with Total column)
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

    # footer payment and memo
    p.setFont("Helvetica", 8)
    p.drawString(left_x, y, f"Payment Method : {invoice.payment_method.title()}")
    y -= 12
    try:
        from num2words import num2words
        words = num2words(invoice.total_amount, lang='en').replace(' and', '').title() + ' Birr Only'
    except Exception:
        words = ''
    p.drawString(left_x, y, f"Amount In Words: {words}")
    y -= 12
    p.drawString(left_x, y, f"MEMO: {invoice.notes or '-'}")

    p.showPage()
    p.save()

    return response
>>>>>>> 8f6d5a6faa537f99b7aab118429879e683d07a2b
