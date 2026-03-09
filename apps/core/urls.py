from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    # Home page
    path('', views.home, name='home'),
    
    # API endpoints
    path('api/set-company/<int:company_id>/', views.set_company, name='set_company'),
    
    # Dashboard
    path('dashboard/', views.dashboard, name='dashboard'),
    
    # Item URLs
    path('items/', views.item_list, name='item_list'),
    path('items/create/', views.item_create, name='item_create'),
    path('items/<int:item_id>/', views.item_detail, name='item_detail'),
    path('items/<int:item_id>/edit/', views.item_edit, name='item_edit'),
    path('items/<int:item_id>/delete/', views.item_delete, name='item_delete'),
    
    # Unit URLs
    path('units/', views.unit_list, name='unit_list'),
    path('units/create/', views.unit_create, name='unit_create'),
    path('units/<int:unit_id>/edit/', views.unit_edit, name='unit_edit'),
    
    # AJAX endpoints
    path('ajax/search-items/', views.ajax_search_items, name='ajax_search_items'),
    path('ajax/item/<int:item_id>/', views.ajax_item_detail, name='ajax_item_detail'),
    
    # Export URLs
    path('export/items/', views.export_items, name='export_items'),
    path('export/units/', views.export_units, name='export_units'),
    
    # Bulk operations
    path('bulk-update/', views.bulk_item_update, name='bulk_item_update'),
]