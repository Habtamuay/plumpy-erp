from django.urls import path
from . import views

app_name = 'sales'

urlpatterns = [
    # ============================
    # Dashboard
    # ============================
    path('', views.dashboard, name='dashboard'),
    path('dashboard/', views.dashboard, name='dashboard'),
    
    # ============================
    # Sales Order URLs
    # ============================
    path('orders/', views.order_list, name='order_list'),
    path('orders/create/', views.order_create, name='order_create'),
    path('orders/<int:order_id>/', views.order_detail, name='order_detail'),
    path('orders/<int:order_id>/edit/', views.order_edit, name='order_edit'),
    path('orders/<int:order_id>/confirm/', views.order_confirm, name='order_confirm'),
    path('orders/<int:order_id>/cancel/', views.order_cancel, name='order_cancel'),
    path('orders/export/', views.export_orders, name='export_orders'),
    path('get-sales-order-details/', views.get_sales_order_details, name='get_sales_order_details'),
    path('get-invoice-details/', views.get_invoice_details, name='get_invoice_details'),
    
    # ============================
    # Sales Invoice URLs
    # ============================
    path('invoices/', views.invoice_list, name='invoice_list'),
    path('invoices/create/', views.invoice_create, name='invoice_create'),
    path('invoices/create-from-order/<int:order_id>/', views.create_invoice_from_order, name='create_invoice_from_order'),
    path('invoices/<int:invoice_id>/', views.invoice_detail, name='invoice_detail'),
    path('invoices/<int:invoice_id>/send/', views.invoice_send, name='invoice_send'),
    path('invoices/<int:invoice_id>/cancel/', views.invoice_cancel, name='invoice_cancel'),
    path('customers/<int:customer_id>/history/', views.customer_history, name='customer_history'),
    # ============================
    # Shipment URLs
    # ============================
    path('shipments/', views.shipment_list, name='shipment_list'),
    path('shipments/create/<int:order_id>/', views.create_shipment, name='create_shipment'),
    path('shipments/<int:shipment_id>/', views.shipment_detail, name='shipment_detail'),
    path('shipments/<int:shipment_id>/ship/', views.shipment_ship, name='shipment_ship'),
    path('shipments/<int:shipment_id>/deliver/', views.shipment_deliver, name='shipment_deliver'),
    
    # ============================
    # Payment URLs
    # ============================
    path('payments/', views.payment_list, name='payment_list'),
    path('payments/create/<int:invoice_id>/', views.payment_create, name='payment_create'),
    
    # ============================
    # AJAX URLs
    # ============================
    path('ajax/order-lines/<int:order_id>/', views.ajax_order_lines, name='ajax_order_lines'),
    path('ajax/item-price/<int:item_id>/<int:customer_id>/', views.ajax_item_price, name='ajax_item_price'),
]