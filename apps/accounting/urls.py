from django.urls import path
from . import views
from . import financial_views

app_name = 'accounting'

urlpatterns = [
    # Dashboard
    path('', views.dashboard, name='dashboard'),
    path('dashboard/', views.dashboard, name='dashboard'),
    
    # AR/AP Dashboards
    path('ar-dashboard/', views.ar_dashboard, name='ar_dashboard'),
    path('ap-dashboard/', views.ap_dashboard, name='ap_dashboard'),
    
    # Aging Reports
    path('ar-aging/', views.ar_aging_report, name='ar_aging'),
    path('ap-aging/', views.ap_aging_report, name='ap_aging'),
    
    # Financial Reports
    path('trial-balance/', views.trial_balance, name='trial_balance'),
    path('chart-of-accounts/', views.chart_of_accounts, name='chart_of_accounts'),
    path('general-ledger/', views.general_ledger, name='general_ledger'),
    
    # Payment Management
    path('payment-entry/', views.payment_entry, name='payment_entry'),
    path('reconciliation/', views.payment_reconciliation, name='payment_reconciliation'),
    path('reconcile/<int:payment_id>/', views.reconcile_payment, name='reconcile_payment'),
    
    # Fiscal Periods
    path('fiscal-periods/', views.fiscal_period_list, name='fiscal_period_list'),
    path('fiscal-periods/create/', views.fiscal_period_create, name='fiscal_period_create'),
    path('fiscal-periods/<int:period_id>/', views.fiscal_period_detail, name='fiscal_period_detail'),
    path('fiscal-periods/<int:period_id>/close/', views.fiscal_period_close, name='fiscal_period_close'),

    # Financial Reporting Engine (General Ledger based)
    path('financial/trial-balance/', financial_views.financial_trial_balance, name='financial_trial_balance'),
    path('financial/profit-and-loss/', financial_views.financial_profit_and_loss, name='financial_profit_and_loss'),
    path('financial/balance-sheet/', financial_views.financial_balance_sheet, name='financial_balance_sheet'),
    path('financial/cash-flow/', financial_views.financial_cash_flow, name='financial_cash_flow'),
]
