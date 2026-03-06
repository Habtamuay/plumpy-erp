document.addEventListener('DOMContentLoaded', function() {
    const invoiceSelect = document.querySelector('#id_invoice');
    if (!invoiceSelect) return;

    function fetchInvoiceData(invoiceId) {
        if (!invoiceId) return;
        fetch(`/sales/get-invoice-details/?invoice_id=${invoiceId}`)
            .then(resp => resp.json())
            .then(data => {
                if (data.success) {
                    document.querySelector('#id_customer_name').value = data.customer_name || '';
                    document.querySelector('#id_invoice_total').value = data.total_amount || '';
                    document.querySelector('#id_remaining').value = data.remaining || '';
                    document.querySelector('#id_payment_status').value = data.status || '';
                }
            })
            .catch(console.error);
    }

    invoiceSelect.addEventListener('change', function() {
        fetchInvoiceData(this.value);
    });

    // on load, if invoice already selected
    if (invoiceSelect.value) {
        fetchInvoiceData(invoiceSelect.value);
    }
});