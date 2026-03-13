from django.urls import path
from . import views

app_name = 'purchasing'

urlpatterns = [
    # Dashboard
    path('', views.dashboard, name='dashboard'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('suppliers/dashboard/', views.supplier_dashboard, name='supplier_dashboard'),

    # Purchase Orders - Support both 'po' and 'pos'
    # List views
    path('pos/', views.po_list, name='po_list'),
    path('po/', views.po_list, name='po_list_alt'),
    
    # Create view - This is the one causing the 404
    path('pos/create/', views.po_create, name='po_create'),
    path('po/create/', views.po_create, name='po_create_alt'),
    
    # Detail view
    path('pos/<int:po_id>/', views.po_detail, name='po_detail'),
    path('po/<int:po_id>/', views.po_detail, name='po_detail_alt'),
    
    # Edit view
    path('pos/<int:po_id>/edit/', views.po_edit, name='po_edit'),
    path('po/<int:po_id>/edit/', views.po_edit, name='po_edit_alt'),
    
    # Delete view
    path('pos/<int:po_id>/delete/', views.po_delete, name='po_delete'),
    path('po/<int:po_id>/delete/', views.po_delete, name='po_delete_alt'),
    
    # Print view
    path('pos/<int:po_id>/print/', views.po_print, name='po_print'),
    path('po/<int:po_id>/print/', views.po_print, name='po_print_alt'),
    
    # Download PDF
    path('pos/<int:po_id>/download/', views.download_po_pdf, name='download_po_pdf'),
    path('po/<int:po_id>/download/', views.download_po_pdf, name='download_po_pdf_alt'),

    # PO Actions
    path('pos/<int:po_id>/send/', views.po_send, name='po_send'),
    path('po/<int:po_id>/send/', views.po_send, name='po_send_alt'),
    
    path('pos/<int:po_id>/receive/', views.receive_po, name='receive_po'),
    path('po/<int:po_id>/receive/', views.receive_po, name='receive_po_alt'),
    
    path('pos/<int:po_id>/cancel/', views.po_cancel, name='po_cancel'),
    path('po/<int:po_id>/cancel/', views.po_cancel, name='po_cancel_alt'),
    
    path('pos/<int:po_id>/close/', views.po_close, name='po_close'),
    path('po/<int:po_id>/close/', views.po_close, name='po_close_alt'),

    # Suppliers
    path('suppliers/', views.supplier_list, name='supplier_list'),
    path('suppliers/create/', views.supplier_create, name='supplier_create'),
    path('suppliers/<int:supplier_id>/', views.supplier_detail, name='supplier_detail'),
    path('suppliers/<int:supplier_id>/edit/', views.supplier_edit, name='supplier_edit'),
    path('suppliers/<int:supplier_id>/delete/', views.supplier_delete, name='supplier_delete'),
    path('suppliers/<int:supplier_id>/performance/', views.supplier_performance, name='supplier_performance'),
    path('suppliers/export/', views.export_suppliers, name='export_suppliers'),
    
    # Requisitions
    path('requisitions/', views.requisition_list, name='requisition_list'),
    path('requisitions/create/', views.requisition_create, name='requisition_create'),
    path('requisitions/<int:requisition_id>/', views.requisition_detail, name='requisition_detail'),

    # Goods Receipts
    path('receipts/', views.goods_receipt_list, name='goods_receipt_list'),
    path('receipts/create/', views.goods_receipt_create, name='goods_receipt_create'),
    path('receipts/<int:receipt_id>/', views.goods_receipt_detail, name='goods_receipt_detail'),

    # Reports
    path('reports/', views.purchasing_report, name='purchasing_report'),
    path('reports/spend-analysis/', views.spend_analysis, name='spend_analysis_report'),
    path('reports/lead-time/', views.lead_time_report, name='lead_time_report'),
    path('reports/po-status/', views.po_status_report, name='po_status_report'),

    # AJAX Endpoints
    path('ajax/supplier-info/<int:supplier_id>/', views.ajax_supplier_info, name='ajax_supplier_info'),
    path('ajax/po-lines/<int:po_id>/', views.ajax_po_lines, name='ajax_po_lines'),
    path('ajax/item-price/<int:item_id>/<int:supplier_id>/', views.ajax_item_price, name='ajax_item_price'),
    path('ajax/check-po-number/', views.ajax_check_po_number, name='ajax_check_po_number'),
    path('ajax/check-receipt-number/', views.ajax_check_receipt_number, name='ajax_check_receipt_number'),
]
