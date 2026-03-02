from django.urls import path
from . import views

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
]