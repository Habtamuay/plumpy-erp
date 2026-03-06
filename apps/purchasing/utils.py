from io import BytesIO
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors

def generate_po_pdf(po):
    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    
    # Header
    p.setFont("Helvetica-Bold", 16)
    p.drawString(50, 800, f"PURCHASE ORDER: {po.po_number}")
    
    p.setFont("Helvetica", 10)
    p.drawString(50, 780, f"Date: {po.order_date}")
    p.drawString(50, 765, f"Supplier: {po.supplier.name}")
    
    # Table Header
    p.line(50, 740, 550, 740)
    p.drawString(55, 725, "Item")
    p.drawString(300, 725, "Qty")
    p.drawString(400, 725, "Price")
    p.drawString(500, 725, "Total")
    p.line(50, 720, 550, 720)
    
    # Lines
    y = 700
    for line in po.lines.all():
        p.drawString(55, y, str(line.item.name)[:40])
        p.drawString(300, y, str(line.quantity_ordered))
        p.drawString(400, y, f"{line.unit_price:.2f}")
        p.drawString(500, y, f"{(line.quantity_ordered * line.unit_price):.2f}")
        y -= 20
    
    p.line(50, y, 550, y)
    p.drawString(400, y-20, f"Grand Total: {po.total_amount:.2f}")
    
    p.showPage()
    p.save()
    buffer.seek(0)
    return buffer