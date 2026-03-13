from django.urls import path
from . import views

app_name = 'reports'

urlpatterns = [
    # API endpoints for charts
    path('api/revenue-trend/', views.api_revenue_trend, name='api_revenue_trend'),
    path('api/sales-by-product/', views.api_sales_by_product, name='api_sales_by_product'),
    path('api/inventory-by-category/', views.api_inventory_by_category, name='api_inventory_by_category'),

    # Financial Reports
    path('financial/balance-sheet/', views.balance_sheet_report, name='balance_sheet'),
    path('financial/profit-loss/', views.profit_loss_report, name='profit_loss'),
    path('financial/cash-flow/', views.cash_flow_report, name='cash_flow'),
    path('financial/trial-balance/', views.trial_balance_report, name='trial_balance'),
    path('financial/general-ledger/', views.general_ledger, name='general_ledger'),
    path('financial/sales-journal/', views.sales_journal, name='sales_journal'),
    path('financial/purchase-journal/', views.purchase_journal, name='purchase_journal'),
    path('financial/cash-payment-journal/', views.cash_payment_journal, name='cash_payment_journal'),
    path('financial/receipt-journal/', views.receipt_journal, name='receipt_journal'),
    path('financial/inventory-journal/', views.inventory_journal, name='inventory_journal'),
    path('financial/ar-aging/', views.ar_aging_report, name='ar_aging'),
    path('financial/ap-aging/', views.ap_aging_report, name='ap_aging'),

    # Inventory Reports
    path('inventory/stock-summary/', views.stock_summary_report, name='stock_summary'),
    path('inventory/stock-value/', views.stock_value_report, name='stock_value'),
    path('inventory/stock-aging/', views.stock_aging_report, name='stock_aging'),
    path('inventory/expiry/', views.expiry_report, name='expiry_report'),
    path('inventory/low-stock/', views.low_stock_report, name='low_stock_report'),
    path('inventory/movements/', views.inventory_movements_report, name='inventory_movements'),

    # Sales Reports
    path('sales/revenue-analysis/', views.revenue_analysis_report, name='revenue_analysis'),
    path('sales/product-sales/', views.product_sales_report, name='product_sales'),
    path('sales/customer-performance/', views.customer_performance_report, name='customer_performance'),
    
    # Purchasing Reports
    path('purchasing/supplier-performance/', views.supplier_performance_report, name='supplier_performance'),
    path('purchasing/spend-analysis/', views.spend_analysis_report, name='spend_analysis'),
    path('purchasing/po-summary/', views.po_summary_report, name='po_summary'),
    path('purchasing/lead-time/', views.lead_time_report, name='lead_time_report'),

    # Production Reports
    path('production/runs/', views.production_runs_report, name='production_runs'),
    path('production/yield/', views.production_yield_report, name='production_yield'),
    path('production/cost-variance/', views.cost_variance_report, name='cost_variance'),
    path('production/consumption/', views.consumption_report, name='consumption_report'),

    # Custom Reports
    path('custom/kpi-dashboard/', views.kpi_dashboard, name='kpi_dashboard'),
    path('custom/comparative-analysis/', views.comparative_analysis, name='comparative_analysis'),
    path('custom/executive-summary/', views.executive_summary, name='executive_summary'),
]