from django.urls import path
from . import views

app_name = 'reports'

urlpatterns = [
    # Dashboard
    path('', views.dashboard, name='dashboard'),
    path('dashboard/', views.dashboard, name='dashboard'),
    
    # ============================
    # Inventory Reports
    # ============================
    path('inventory/stock-summary/', views.stock_summary_report, name='stock_summary'),
    path('inventory/stock-value/', views.stock_value_report, name='stock_value'),
    path('inventory/stock-aging/', views.stock_aging_report, name='stock_aging'),
    path('inventory/low-stock/', views.low_stock_report, name='low_stock'),
    path('inventory/expiry/', views.expiry_report, name='expiry_report'),
    path('inventory/movements/', views.inventory_movements_report, name='inventory_movements'),
    
    # ============================
    # Production Reports
    # ============================
    path('production/runs/', views.production_runs_report, name='production_runs'),
    path('production/cost-variance/', views.cost_variance_report, name='cost_variance'),
    path('production/yield/', views.production_yield_report, name='production_yield'),
    path('production/consumption/', views.material_consumption_report, name='material_consumption'),
    
    # ============================
    # Purchasing Reports
    # ============================
    path('purchasing/po-summary/', views.po_summary_report, name='po_summary'),
    path('purchasing/supplier-performance/', views.supplier_performance_report, name='supplier_performance'),
    path('purchasing/spend-analysis/', views.spend_analysis_report, name='spend_analysis'),
    path('purchasing/lead-time/', views.lead_time_report, name='lead_time'),
    
    # ============================
    # Sales Reports
    # ============================
    path('sales/revenue-analysis/', views.revenue_analysis_report, name='revenue_analysis'),
    path('sales/customer-performance/', views.customer_performance_report, name='customer_performance'),
    path('sales/product-sales/', views.product_sales_report, name='product_sales'),
    
    # ============================
    # Financial Reports
    # ============================
    path('financial/profit-loss/', views.profit_loss_report, name='profit_loss'),
    path('financial/balance-sheet/', views.balance_sheet_report, name='balance_sheet'),
    path('financial/cash-flow/', views.cash_flow_report, name='cash_flow'),
    path('financial/trial-balance/', views.trial_balance_report, name='trial_balance'),
    path('financial/accounts-receivable/', views.accounts_receivable_report, name='ar_report'),
    path('financial/accounts-payable/', views.accounts_payable_report, name='ap_report'),
    path('financial/general-ledger/', views.general_ledger_report, name='general_ledger'),
    path('financial/cash-payment-journal/', views.cash_payment_journal, name='cash_payment_journal'),
    path('financial/sales-journal/', views.sales_journal, name='sales_journal'),
    path('financial/receipt-journal/', views.receipt_journal, name='receipt_journal'),
    path('financial/purchase-journal/', views.purchase_journal, name='purchase_journal'),
    path('financial/inventory-journal/', views.inventory_journal, name='inventory_journal'),
    
    # ============================
    # Custom Reports
    # ============================
    path('custom/executive-summary/', views.executive_summary, name='executive_summary'),
    path('custom/kpi-dashboard/', views.kpi_dashboard, name='kpi_dashboard'),
    path('custom/comparative-analysis/', views.comparative_analysis, name='comparative_analysis'),
    
    # ============================
    # Scheduled Reports
    # ============================
    path('scheduled/', views.scheduled_reports_list, name='scheduled_reports'),
    path('scheduled/create/', views.create_scheduled_report, name='create_scheduled_report'),
    path('scheduled/<int:report_id>/edit/', views.edit_scheduled_report, name='edit_scheduled_report'),
    path('scheduled/<int:report_id>/delete/', views.delete_scheduled_report, name='delete_scheduled_report'),
    path('scheduled/<int:report_id>/run/', views.run_scheduled_report, name='run_scheduled_report'),
]