(function($) {
    $(document).ready(function() {
        // Function to load sales order details
        function loadSalesOrderDetails(orderId) {
            if (!orderId) return;
            
            $.ajax({
                url: '/admin/sales/get-sales-order-details/',
                data: {
                    'order_id': orderId
                },
                dataType: 'json',
                success: function(data) {
                    if (data.success) {
                        // Populate customer field
                        if (data.customer_id) {
                            $('#id_customer').val(data.customer_id).trigger('change');
                        }
                        
                        // Clear existing invoice lines
                        $('.dynamic-salesinvoiceline').remove();
                        
                        // Add new lines for each order line
                        if (data.lines && data.lines.length > 0) {
                            data.lines.forEach(function(line, index) {
                                addInvoiceLine(line, index);
                            });
                        }
                        
                        // Update totals
                        if (data.total_amount) {
                            $('#id_total_amount').val(data.total_amount);
                        }
                        
                        showMessage('Sales order loaded successfully', 'success');
                    }
                },
                error: function() {
                    showMessage('Error loading sales order details', 'error');
                }
            });
        }
        
        // Function to add an invoice line
        function addInvoiceLine(line, index) {
            var template = $('#invoice-line-template').html();
            var newRow = template.replace(/__prefix__/g, index);
            $('#invoice-lines tbody').append(newRow);
            
            // Set values
            var row = $('#invoice-lines tbody tr:last');
            row.find('.field-item select').val(line.item_id).trigger('change');
            row.find('.field-quantity input').val(line.quantity);
            row.find('.field-unit select').val(line.unit_id).trigger('change');
            row.find('.field-unit_price input').val(line.unit_price);
            row.find('.field-discount_percent input').val(line.discount_percent || 0);
            
            // Calculate total
            calculateLineTotal(row);
        }
        
        // Function to calculate line total
        function calculateLineTotal(row) {
            var qty = parseFloat(row.find('.field-quantity input').val()) || 0;
            var price = parseFloat(row.find('.field-unit_price input').val()) || 0;
            var discount = parseFloat(row.find('.field-discount_percent input').val()) || 0;
            
            var subtotal = qty * price;
            var discountAmount = subtotal * (discount / 100);
            var total = subtotal - discountAmount;
            
            row.find('.field-total_price input').val(total.toFixed(2));
        }
        
        // Function to show messages
        function showMessage(message, type) {
            var msgDiv = $('<div class="alert alert-' + type + '">' + message + '</div>');
            $('.messagelist').remove();
            $('#content').before('<ul class="messagelist"></ul>');
            $('.messagelist').append('<li class="' + type + '">' + message + '</li>');
        }
        
        // Trigger when sales order is selected
        $('#id_sales_order').on('change', function() {
            var orderId = $(this).val();
            if (orderId) {
                loadSalesOrderDetails(orderId);
            }
        });
        
        // Add template for new lines
        var template = '<tr class="dynamic-salesinvoiceline">' +
            '<td class="field-item"><select name="salesinvoiceline_set-__prefix__-item"></select></td>' +
            '<td class="field-quantity"><input type="number" name="salesinvoiceline_set-__prefix__-quantity" /></td>' +
            '<td class="field-unit"><select name="salesinvoiceline_set-__prefix__-unit"></select></td>' +
            '<td class="field-unit_price"><input type="number" name="salesinvoiceline_set-__prefix__-unit_price" /></td>' +
            '<td class="field-discount_percent"><input type="number" name="salesinvoiceline_set-__prefix__-discount_percent" /></td>' +
            '<td class="field-total_price"><input type="text" readonly name="salesinvoiceline_set-__prefix__-total_price" /></td>' +
            '<td class="delete"><a href="#" class="inline-deletelink">Remove</a></td>' +
            '</tr>';
        
        $('body').append('<div id="invoice-line-template" style="display:none;">' + template + '</div>');
    });
})(django.jQuery);