"""
URL configuration for plumpy_erp project.
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import RedirectView

urlpatterns = [
    # Admin site
    path('admin/', admin.site.urls),
    
    # App URLs
    path('', RedirectView.as_view(url='/dashboard/'), name='home'),  # Redirect root to dashboard
    path('', include('apps.core.urls')),  # No namespace
    
    
    # Core modules
    path('company/', include('apps.company.urls')),
    
    # Production modules
    path('production/', include('apps.production.urls')),
    path('inventory/', include('apps.inventory.urls')),
    path('purchasing/', include('apps.purchasing.urls')),
    path('sales/', include('apps.sales.urls')),
    
    # Financial modules
    path('accounting/', include('apps.accounting.urls')),
    path('reports/', include('apps.reports.urls')),
    
    # Future modules (commented out until ready)
    # path('quality/', include('apps.quality.urls')),
    # path('supply-chain/', include('apps.supply_chain.urls')),
    # path('resource/', include('apps.resource.urls')),
    # path('costing/', include('apps.costing.urls')),
    # path('compliance/', include('apps.compliance.urls')),
    # path('crm/', include('apps.crm.urls')),
    # path('analytics/', include('apps.analytics.urls')),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_URL)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    
    # Debug toolbar (optional - uncomment if installed)
    # try:
    #     import debug_toolbar
    #     urlpatterns = [path('__debug__/', include(debug_toolbar.urls))] + urlpatterns
    # except ImportError:
    #     pass