from django.urls import path
from . import views

app_name = 'company'

urlpatterns = [
    # Dashboard
    path('', views.company_dashboard, name='dashboard'),
    path('dashboard/', views.company_dashboard, name='dashboard'),
    
    # Company URLs
    path('list/', views.company_list, name='company_list'),
    path('<int:company_id>/', views.company_detail, name='company_detail'),
    
    # Branch URLs
    path('branches/', views.branch_list, name='branch_list'),
    path('branches/<int:branch_id>/', views.branch_detail, name='branch_detail'),
    
    # Department URLs
    path('departments/', views.department_list, name='department_list'),
    path('departments/<int:department_id>/', views.department_detail, name='department_detail'),
    
    # Customer URLs
    path('customers/', views.customer_list, name='customer_list'),
    path('customers/<int:pk>/', views.customer_detail, name='customer_detail'),
    path('customers/<int:customer_id>/ledger/', views.customer_ledger, name='customer_ledger'),
    
    # Supplier URLs
    path('suppliers/<int:supplier_id>/ledger/', views.supplier_ledger, name='supplier_ledger'),
    
    # User Profile URLs
    path('profile/', views.user_profile, name='user_profile'),
    path('profile/<int:user_id>/', views.user_profile_detail, name='user_profile_detail'),
    path('users/', views.user_list, name='user_list'),
    
    # Export URLs
    path('export/customers/', views.export_customers, name='export_customers'),
]