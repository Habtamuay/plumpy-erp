from django.urls import path
from . import views

app_name = 'inventory'

urlpatterns = [
    # Dashboard
    path('', views.dashboard, name='dashboard'),
    path('dashboard/', views.dashboard, name='dashboard'),
    
    # Warehouse URLs
    path('warehouses/', views.warehouse_list, name='warehouse_list'),
    path('warehouses/<int:warehouse_id>/', views.warehouse_detail, name='warehouse_detail'),
    
    # Lot/Batch URLs
    path('lots/', views.lot_list, name='lot_list'),
    path('lots/<int:lot_id>/', views.lot_detail, name='lot_detail'),
    
    # Transaction URLs
    path('transactions/', views.transaction_list, name='transaction_list'),
    path('transactions/<int:transaction_id>/', views.transaction_detail, name='transaction_detail'),
    
    # Current Stock URLs
    path('current-stock/', views.current_stock, name='current_stock'),
    path('stock-ledger/', views.stock_ledger, name='stock_ledger'),
    
    # Report URLs
    path('stock-summary/', views.stock_summary, name='stock_summary'),
    path('consumption-vs-bom/', views.consumption_vs_bom, name='consumption_vs_bom'),
    path('low-stock/', views.low_stock_alerts, name='low_stock_alerts'),
    path('low-stock-widget/', views.low_stock_widget, name='low_stock_widget'),
    path('analytics/', views.inventory_analytics, name='inventory_analytics'),
    path('trends/', views.inventory_trends, name='inventory_trends'),
    
    
    # Export URLs
    path('export/transactions/', views.export_transactions, name='export_transactions'),
    
    # AJAX URLs
    path('ajax/lot/<int:lot_id>/', views.ajax_lot_info, name='ajax_lot_info'),
    path('ajax/warehouse/<int:warehouse_id>/stock/', views.ajax_warehouse_stock, name='ajax_warehouse_stock'),
]
