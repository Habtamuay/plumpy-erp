from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User
from django.utils.html import format_html
from .models import Company, Branch, Customer, UserProfile, Department


class UserProfileInline(admin.StackedInline):
    """Inline for UserProfile to show in User admin page"""
    model = UserProfile
    can_delete = False
    verbose_name_plural = 'Profile'
    fk_name = 'user'
    fields = ('company', 'branch', 'department', 'employee_id', 'role', 'phone', 'is_active')
    extra = 0
    autocomplete_fields = ['company', 'branch', 'department']


class CustomUserAdmin(UserAdmin):
    """Custom User admin with UserProfile inline"""
    inlines = [UserProfileInline]
    list_display = ('username', 'email', 'first_name', 'last_name', 'is_staff', 'get_company', 'get_profile_status')
    list_select_related = ('profile',)  # Changed from 'userprofile' to 'profile'
    search_fields = ('username', 'email', 'first_name', 'last_name')
    
    def get_company(self, instance):
        """Get user's company from profile"""
        try:
            return instance.profile.company.name
        except (UserProfile.DoesNotExist, AttributeError):
            return '-'
    get_company.short_description = 'Company'
    
    def get_profile_status(self, instance):
        """Show profile status with icon"""
        try:
            if instance.profile.is_active:
                return format_html('<span style="color: green;">✓ Active</span>')
            else:
                return format_html('<span style="color: orange;">⚠ Inactive</span>')
        except (UserProfile.DoesNotExist, AttributeError):
            return format_html('<span style="color: gray;">✗ No Profile</span>')
    get_profile_status.short_description = 'Profile'
    
    def get_inline_instances(self, request, obj=None):
        """Only show inline when editing existing user"""
        if not obj:
            return list()
        return super().get_inline_instances(request, obj)


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ('name', 'tin_number', 'phone', 'email', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('name', 'tin_number', 'email', 'legal_name')
    readonly_fields = ('created_at', 'updated_at')
    list_per_page = 25
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'legal_name', 'tin_number', 'is_active')
        }),
        ('Contact Details', {
            'fields': ('address', 'phone', 'email')
        }),
        ('Branding', {
            'fields': ('logo',),
            'classes': ('wide',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'company', 'is_main', 'is_active', 'city_display')
    list_filter = ('company', 'is_main', 'is_active')
    search_fields = ('name', 'code', 'company__name', 'city')
    list_editable = ('is_main', 'is_active')
    autocomplete_fields = ['company']
    list_per_page = 25
    
    fieldsets = (
        ('Branch Information', {
            'fields': ('company', 'name', 'code', 'is_main', 'is_active')
        }),
        ('Location', {
            'fields': ('address', 'city', 'country')
        }),
    )
    
    def city_display(self, obj):
        return obj.city or '-'
    city_display.short_description = 'City'


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'company', 'branch', 'manager', 'is_active')
    list_filter = ('company', 'branch', 'is_active')
    search_fields = ('name', 'code', 'company__name')
    autocomplete_fields = ['company', 'branch', 'manager']
    list_per_page = 25


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ('name', 'company', 'tin', 'phone', 'email', 'credit_limit', 'status_badge')
    list_filter = ('company', 'is_active')
    search_fields = ('name', 'tin', 'email', 'phone')
    autocomplete_fields = ['company']
    list_per_page = 25
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('company', 'name', 'tin', 'is_active')
        }),
        ('Contact Details', {
            'fields': ('phone', 'email', 'address')
        }),
        ('Financial', {
            'fields': ('credit_limit',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def status_badge(self, obj):
        if obj.is_active:
            return format_html('<span style="color: green;">✓ Active</span>')
        return format_html('<span style="color: red;">✗ Inactive</span>')
    status_badge.short_description = 'Status'


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user_info', 'company', 'branch', 'department', 'role', 'employee_id', 'status_badge')
    list_filter = ('company', 'branch', 'department', 'role', 'is_active')
    search_fields = ('user__username', 'user__email', 'user__first_name', 'user__last_name', 'employee_id')
    raw_id_fields = ('user',)
    autocomplete_fields = ['company', 'branch', 'department']
    list_per_page = 25
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        ('User', {
            'fields': ('user', 'is_active')
        }),
        ('Company Assignment', {
            'fields': ('company', 'branch', 'department')
        }),
        ('Employment Details', {
            'fields': ('employee_id', 'job_title', 'role', 'phone', 'mobile')
        }),
        ('Personal Information', {
            'fields': ('date_of_birth', 'hire_date', 'emergency_contact', 'emergency_phone'),
            'classes': ('collapse',)
        }),
        ('Address', {
            'fields': ('address', 'city', 'country'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def user_info(self, obj):
        """Display user info with username and full name"""
        full_name = obj.user.get_full_name()
        if full_name:
            return format_html(
                '{}<br><small style="color: #666;">@{}</small>',
                full_name,
                obj.user.username
            )
        return format_html(
            '{}<br><small style="color: #666;">No name set</small>',
            obj.user.username
        )
    user_info.short_description = 'User'
    user_info.admin_order_field = 'user__username'
    
    def status_badge(self, obj):
        """Display status as a colored badge"""
        if obj.is_active:
            return format_html('<span style="background-color: #28a745; color: white; padding: 3px 8px; border-radius: 3px;">Active</span>')
        return format_html('<span style="background-color: #dc3545; color: white; padding: 3px 8px; border-radius: 3px;">Inactive</span>')
    status_badge.short_description = 'Status'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user', 'company', 'branch', 'department')


# Re-register User with custom UserAdmin
admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)