from django.urls import path
from . import views

app_name = 'production'

urlpatterns = [
    # Dashboard
    path('', views.dashboard, name='dashboard'),
    path('dashboard/', views.dashboard, name='dashboard'),
    
    # Production Runs
    path('runs/', views.production_run_list, name='production_run_list'),
    path('runs/start/', views.start_production_run, name='start_run'),
    path('runs/<int:pk>/start/', views.start_existing_run, name='start_existing_run'),
    path('runs/<int:pk>/edit/', views.edit_production_run, name='edit_run'),
    path('runs/<int:pk>/', views.production_run_detail, name='production_run_detail'),
    path('runs/<int:pk>/complete/', views.complete_production_run, name='complete_run'),
    path('runs/<int:pk>/cancel/', views.cancel_production_run, name='cancel_run'),
    
    # BOM (Bill of Materials)
    path('boms/', views.bom_list, name='bom_list'),
    path('boms/<int:pk>/', views.bom_detail, name='bom_detail'),
    
    # Inventory Movements
    path('movements/', views.movement_list, name='movement_list'),
    path('movements/<int:pk>/', views.movement_detail, name='movement_detail'),
    
    # Reports
    path('reports/cost-variance/', views.cost_variance_report, name='cost_variance_report'),
    path('reports/cost-variance/simple/', views.production_cost_variance_report, name='cost_variance_report_simple'),
    
    # AJAX endpoints
    path('ajax/bom/<int:bom_id>/', views.ajax_bom_details, name='ajax_bom_details'),
]
