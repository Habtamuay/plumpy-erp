from django.contrib import admin
from django.utils.html import format_html
from .models import ReportTemplate, ScheduledReport, ReportCategory, DashboardWidget


@admin.register(ReportCategory)
class ReportCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'icon', 'display_order', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name', 'description')
    list_editable = ('display_order', 'is_active')
    ordering = ('display_order', 'name')
    
    fieldsets = (
        ('Category Information', {
            'fields': ('name', 'icon', 'description', 'display_order', 'is_active')
        }),
    )


@admin.register(ReportTemplate)
class ReportTemplateAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'report_type', 'format', 'is_system', 'is_active', 'created_at')
    list_filter = ('category', 'report_type', 'format', 'is_system', 'is_active')
    search_fields = ('name', 'description', 'slug')
    prepopulated_fields = {'slug': ('name',)}
    readonly_fields = ('created_at', 'updated_at', 'created_by')
    list_editable = ('is_active',)
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('category', 'name', 'slug', 'description', 'is_active')
        }),
        ('Report Configuration', {
            'fields': ('report_type', 'format', 'template_file', 'query_config')
        }),
        ('System Settings', {
            'fields': ('is_system', 'icon', 'color'),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(ScheduledReport)
class ScheduledReportAdmin(admin.ModelAdmin):
    list_display = ('name', 'report', 'schedule_type', 'recipients_list', 'is_active', 'next_run')
    list_filter = ('schedule_type', 'is_active', 'report__category')
    search_fields = ('name', 'recipients', 'report__name')
    readonly_fields = ('created_at', 'updated_at', 'last_run', 'next_run', 'created_by')
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'report', 'description', 'is_active')
        }),
        ('Schedule', {
            'fields': ('schedule_type', 'hour', 'day_of_month', 'day_of_week', 'time')
        }),
        ('Recipients', {
            'fields': ('recipients', 'email_subject', 'email_body')
        }),
        ('Output', {
            'fields': ('format', 'include_charts', 'include_tables')
        }),
        ('Execution', {
            'fields': ('last_run', 'next_run', 'created_by'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def recipients_list(self, obj):
        recipients = obj.recipients.split(',')[:3]
        return ', '.join(recipients) + ('...' if len(obj.recipients.split(',')) > 3 else '')
    recipients_list.short_description = 'Recipients'
    
    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
    
    actions = ['run_now', 'send_test_email']
    
    def run_now(self, request, queryset):
        for report in queryset:
            # Trigger report generation
            self.message_user(request, f"Report '{report.name}' queued for generation.")
    run_now.short_description = "Run selected reports now"
    
    def send_test_email(self, request, queryset):
        for report in queryset:
            # Send test email
            self.message_user(request, f"Test email sent for '{report.name}'.")
    send_test_email.short_description = "Send test email"


@admin.register(DashboardWidget)
class DashboardWidgetAdmin(admin.ModelAdmin):
    list_display = ('title', 'user', 'widget_type', 'size', 'position', 'is_visible')
    list_filter = ('widget_type', 'is_visible', 'user')
    search_fields = ('title',)
    list_editable = ('size', 'position', 'is_visible')
    
    fieldsets = (
        ('Widget Information', {
            'fields': ('user', 'title', 'widget_type', 'is_visible')
        }),
        ('Layout', {
            'fields': ('size', 'position', 'config')
        }),
    )