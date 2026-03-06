from django.urls import path
from . import views
from apps.purchasing.views import download_po_pdf

app_name = 'purchasing'

urlpatterns = [
    # ============================
    # Dashboard
    # ============================
    path('', views.dashboard, name='dashboard'),
    path('dashboard/', views.dashboard, name='dashboard'),
    
    # ============================
    # Supplier URLs
    # ============================
    path('suppliers/', views.supplier_list, name='supplier_list'),
    path('suppliers/dashboard/', views.supplier_dashboard, name='supplier_dashboard'),
    path('suppliers/create/', views.supplier_create, name='supplier_create'),
    path('suppliers/<int:supplier_id>/', views.supplier_detail, name='supplier_detail'),
    path('suppliers/<int:supplier_id>/edit/', views.supplier_edit, name='supplier_edit'),
    path('suppliers/<int:supplier_id>/delete/', views.supplier_delete, name='supplier_delete'),
    path('suppliers/<int:supplier_id>/performance/', views.supplier_performance, name='supplier_performance'),
    path('suppliers/export/', views.export_suppliers, name='export_suppliers'),
    
    # ============================
    # Purchase Requisition URLs
    # ============================
    path('requisitions/', views.requisition_list, name='requisition_list'),
    path('requisitions/create/', views.requisition_create, name='requisition_create'),
    path('requisitions/<int:requisition_id>/', views.requisition_detail, name='requisition_detail'),
    path('requisitions/<int:requisition_id>/edit/', views.requisition_edit, name='requisition_edit'),
    path('requisitions/<int:requisition_id>/delete/', views.requisition_delete, name='requisition_delete'),
    path('requisitions/<int:requisition_id>/submit/', views.requisition_submit, name='requisition_submit'),
    path('requisitions/<int:requisition_id>/approve/', views.requisition_approve, name='requisition_approve'),
    path('requisitions/<int:requisition_id>/reject/', views.requisition_reject, name='requisition_reject'),
    path('requisitions/<int:requisition_id>/create-po/', views.create_po_from_requisition, name='create_po_from_requisition'),
    
    # ============================
    # Purchase Order URLs
    # ============================
    path('pos/', views.po_list, name='po_list'),
    path('pos/create/', views.po_create, name='po_create'),
    path('pos/<int:po_id>/', views.po_detail, name='po_detail'),
    path('pos/<int:po_id>/edit/', views.po_edit, name='po_edit'),
    path('pos/<int:po_id>/delete/', views.po_delete, name='po_delete'),
    path('pos/<int:po_id>/send/', views.po_send, name='po_send'),
    path('pos/<int:po_id>/receive/', views.receive_po, name='receive_po'),
    path('pos/<int:po_id>/close/', views.po_close, name='po_close'),
    path('pos/<int:po_id>/cancel/', views.po_cancel, name='po_cancel'),
    path('pos/<int:po_id>/print/', views.po_print, name='po_print'),
    path('pos/export/', views.export_pos, name='export_pos'),
    path('purchasing/po/<int:po_id>/pdf/', download_po_pdf, name='po_pdf'),
    
    # ============================
    # Goods Receipt URLs
    # ============================
    path('receipts/', views.goods_receipt_list, name='goods_receipt_list'),
    path('receipts/create/', views.goods_receipt_create, name='goods_receipt_create'),
    path('receipts/<int:receipt_id>/', views.goods_receipt_detail, name='goods_receipt_detail'),
    path('receipts/<int:receipt_id>/edit/', views.goods_receipt_edit, name='goods_receipt_edit'),
    path('receipts/<int:receipt_id>/delete/', views.goods_receipt_delete, name='goods_receipt_delete'),
    path('receipts/export/', views.export_receipts, name='export_receipts'),
    
    # ============================
    # Report URLs
    # ============================
    path('reports/', views.purchasing_report, name='purchasing_report'),
    path('reports/spend-analysis/', views.spend_analysis, name='spend_analysis'),
    path('reports/lead-time/', views.lead_time_report, name='lead_time_report'),
    path('reports/po-status/', views.po_status_report, name='po_status_report'),
    
    
    # ============================
    # AJAX URLs (for dynamic loading)
    # ============================
    path('ajax/supplier-info/<int:supplier_id>/', views.ajax_supplier_info, name='ajax_supplier_info'),
    path('ajax/po-lines/<int:po_id>/', views.ajax_po_lines, name='ajax_po_lines'),
    path('ajax/item-price/<int:item_id>/<int:supplier_id>/', views.ajax_item_price, name='ajax_item_price'),
    path('ajax/check-po-number/', views.ajax_check_po_number, name='ajax_check_po_number'),
]


