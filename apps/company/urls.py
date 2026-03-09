from django.urls import path
from . import views

app_name = 'company'

urlpatterns = [
    # Dashboard
    path('', views.company_dashboard, name='dashboard'),
    path('dashboard/', views.company_dashboard, name='dashboard'),
    path('scope-audit/', views.company_scope_audit, name='scope_audit'),
    
    # Company URLs
    path('create/', views.company_create, name='create'),
    path('list/', views.company_list, name='list'),  # URL name is 'list', not 'company_list'
    path('<int:company_id>/', views.company_detail, name='detail'),
    path('<int:company_id>/edit/', views.company_edit, name='edit'),
    path('<int:company_id>/delete/', views.company_delete, name='delete'),
    
    # Branch URLs
    path('branches/', views.branch_list, name='branch_list'),
    path('branches/create/', views.branch_create, name='branch_create'),
    path('branches/<int:branch_id>/', views.branch_detail, name='branch_detail'),
    path('branches/<int:branch_id>/edit/', views.branch_edit, name='branch_edit'),
    path('branches/<int:branch_id>/delete/', views.branch_delete, name='branch_delete'),
    
    # Department URLs
    path('departments/', views.department_list, name='department_list'),
    path('departments/create/', views.department_create, name='department_create'),
    path('departments/<int:department_id>/', views.department_detail, name='department_detail'),
    path('departments/<int:department_id>/edit/', views.department_edit, name='department_edit'),
    path('departments/<int:department_id>/delete/', views.department_delete, name='department_delete'),
    
    # Customer URLs
    path('customers/', views.customer_list, name='customer_list'),
    path('customers/create/', views.customer_create, name='customer_create'),
    path('customers/<int:pk>/', views.customer_detail, name='customer_detail'),
    path('customers/<int:pk>/edit/', views.customer_edit, name='customer_edit'),
    path('customers/<int:pk>/delete/', views.customer_delete, name='customer_delete'),
    path('customers/<int:customer_id>/ledger/', views.customer_ledger, name='customer_ledger'),
    
    # Supplier URLs
    path('suppliers/', views.supplier_list, name='supplier_list'),
    path('suppliers/<int:supplier_id>/', views.supplier_detail, name='supplier_detail'),
    path('suppliers/<int:supplier_id>/ledger/', views.supplier_ledger, name='supplier_ledger'),
    
    # User Profile URLs
    path('profile/', views.user_profile, name='user_profile'),
    path('profile/<int:user_id>/', views.user_profile_detail, name='user_profile_detail'),
    path('users/', views.user_list, name='user_list'),
    
    # Export URLs
    path('export/customers/', views.export_customers, name='export_customers'),
    path('export/companies/', views.export_companies, name='export_companies'),
    path('export/branches/', views.export_branches, name='export_branches'),
    path('export/departments/', views.export_departments, name='export_departments'),
    path('export/company-customers/', views.export_company_customers, name='export_company_customers'),
]
