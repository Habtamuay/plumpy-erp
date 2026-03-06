// static/js/report_exports.js
// Modular export utilities with Chart.js support + header/footer + logo

const ExportUtils = (function() {
    // ────────────────────────────────────────────────
    // === COMPANY LOGO BASE64 ===
    // Replace this with YOUR real base64 string!
    // Keep width/height small (e.g. 120×40 px) for clean header
    const LOGO_BASE64 = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAIAAAACACAYAAADDPmHLAAAAAXNSR0IArs4c6QAAAARnQU1BAACxjwv8YQUAAAAJcEhZcwAADsMAAA7DAcdvqGQAA...'; // ← PASTE YOUR FULL BASE64 HERE

    const LOGO_WIDTH_MM  = 35;   // Adjust to fit your header nicely (A4 landscape ~297mm wide)
    const LOGO_HEIGHT_MM = 18;   // Maintain aspect ratio
    const LOGO_X = 14;           // Left margin
    const LOGO_Y = 8;            // Top position

    // ────────────────────────────────────────────────
    // Private helpers (unchanged parts omitted for brevity)
    // ────────────────────────────────────────────────

    function getReportTitle() {
        return document.querySelector('h1')?.textContent.trim() || document.title.trim() || 'ERP Report';
    }

    function getFilename(extension) {
        const title = getReportTitle().replace(/[^a-z0-9]/gi, '_');
        const date = new Date().toISOString().slice(0, 10);
        return `${title}_${date}.${extension}`;
    }

    // ────────────────────────────────────────────────
    // Header & Footer – NOW WITH LOGO
    // ────────────────────────────────────────────────
    function drawHeaderFooter(doc) {
        const pageWidth = doc.internal.pageSize.getWidth();
        const pageHeight = doc.internal.pageSize.getHeight();
        const margin = 14;

        // ── HEADER ───────────────────────────────────────

        // 1. Logo (left side)
        if (LOGO_BASE64) {
            try {
                doc.addImage(
                    LOGO_BASE64,
                    'PNG',                // or 'JPEG'
                    LOGO_X,
                    LOGO_Y,
                    LOGO_WIDTH_MM,
                    LOGO_HEIGHT_MM
                );
            } catch (e) {
                console.warn('Failed to add logo to PDF header:', e);
                // Fallback: just text if logo fails
                doc.setFontSize(14);
                doc.setTextColor(40);
                doc.setFont("helvetica", "bold");
                doc.text(getReportTitle(), margin, 12);
            }
        }

        // 2. Report title (centered or right of logo)
        doc.setFontSize(14);
        doc.setTextColor(40, 40, 40);
        doc.setFont("helvetica", "bold");
        const titleX = LOGO_X + LOGO_WIDTH_MM + 8; // right of logo
        doc.text(getReportTitle(), titleX, 15);

        // Optional company name below title/logo
        doc.setFontSize(10);
        doc.setFont("helvetica", "normal");
        doc.text("Your Company Name • ERP System", titleX, 23);

        // Right side: generation date
        doc.setFontSize(9);
        doc.setTextColor(100);
        doc.text(`Generated: ${new Date().toLocaleDateString('en-GB')} ${new Date().toLocaleTimeString('en-GB', {timeZone: 'Africa/Addis_Ababa'})}`, 
                 pageWidth - margin, 15, { align: 'right' });

        // Thin line under header
        doc.setLineWidth(0.4);
        doc.setDrawColor(160);
        doc.line(margin, 28, pageWidth - margin, 28);

        // ── FOOTER ───────────────────────────────────────
        doc.setFontSize(9);
        doc.setTextColor(100);

        doc.text("Confidential • Internal Use Only • Habtamu’s ERP", margin, pageHeight - 8);

        doc.text(`Page ${doc.internal.getNumberOfPages()}`, pageWidth / 2, pageHeight - 8, { align: 'center' });

        // Line above footer
        doc.line(margin, pageHeight - 15, pageWidth - margin, pageHeight - 15);
    }

    // ────────────────────────────────────────────────
    // PDF Export – integrate header/footer with logo
    // ────────────────────────────────────────────────
    function toPDF() {
        const tables = document.querySelectorAll('.table');
        const canvases = document.querySelectorAll('canvas');

        if (tables.length === 0 && canvases.length === 0) {
            alert('No content found to export');
            return;
        }

        const { jsPDF } = window.jspdf;
        const doc = new jsPDF({ orientation: 'landscape', unit: 'mm' });

        // Draw initial header
        drawHeaderFooter(doc);

        let y = 34; // Start content below header (increased to fit logo + text)

        // Charts...
        canvases.forEach((canvas, idx) => {
            if (y > 160) {
                doc.addPage();
                drawHeaderFooter(doc);
                y = 34;
            }

            const imgData = canvas.toDataURL('image/png');
            const ratio = canvas.width / canvas.height;
            let w = 170, h = w / ratio;
            if (h > 110) { h = 110; w = h * ratio; }

            doc.addImage(imgData, 'PNG', 14, y, w, h);
            y += h + 10;

            doc.setFontSize(11);
            doc.text(`Chart ${idx + 1}: ${canvas.id || 'Visualization'}`, 14, y);
            y += 12;
        });

        // Tables...
        tables.forEach((table, idx) => {
            if (y > 140 || (canvases.length > 0 && idx === 0)) {
                doc.addPage();
                y = 34;
            }

            doc.autoTable({
                html: table,
                startY: y,
                theme: 'grid',
                headStyles: { fillColor: [66, 139, 202], textColor: 255, fontStyle: 'bold' },
                styles: { fontSize: 9, cellPadding: 3, overflow: 'linebreak' },
                margin: { left: 14, right: 14, top: 34 }, // Respect logo + header space
                didDrawPage: () => {
                    drawHeaderFooter(doc); // Ensures logo + header/footer on every page
                }
            });

            y = doc.lastAutoTable.finalY + 12;
        });

        doc.save(getFilename('pdf'));
    }

    // ... (toCSV, toExcel, downloadBlob remain unchanged)

    return {
        toCSV,
        toExcel,
        toPDF
    };
})();