from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from django.http import HttpResponse


def generate_invoice_pdf(invoice):

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
    p.drawString(left_x+30, y, "Code")
    p.drawString(left_x+90, y, "Description")
    p.drawString(left_x+230, y, "Unit")
    p.drawString(left_x+270, y, "Qty")
    p.drawString(left_x+310, y, "Unit Price")
    p.drawString(left_x+380, y, "Total")
    y -= 14

    p.setFont("Helvetica", 8)

    y -= 20

    line_no = 1
    for line in invoice.lines.all():
        p.drawString(left_x, y, str(line_no))
        p.drawString(left_x+30, y, line.item.code or "")
        p.drawString(left_x+90, y, line.item.name)
        p.drawString(left_x+230, y, line.unit.abbreviation if line.unit else "")
        p.drawString(left_x+270, y, str(line.quantity))
        p.drawString(left_x+310, y, str(line.unit_price))
        p.drawString(left_x+380, y, str(line.total_price))
        y -= 14
        line_no += 1
        if y < 100:
            p.showPage()
            y = 800
    y -= 20

    # totals box on right (shifted further right)
    tx = left_x + 340
    p.setFont("Helvetica-Bold", 9)
    p.drawString(tx, y, "SUBTOTAL")
    p.drawRightString(tx+80, y, str(invoice.subtotal))
    y -= 14
    p.drawString(tx, y, f"VAT({invoice.tax_rate}%)")
    p.drawRightString(tx+80, y, str(invoice.tax_amount))
    y -= 14
    p.drawString(tx, y, "GRAND TOTAL")
    p.drawRightString(tx+80, y, str(invoice.total_amount))
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