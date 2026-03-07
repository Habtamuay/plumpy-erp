from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User
from django.core.validators import RegexValidator, EmailValidator
from apps.core.models import CompanyModel


class Company(models.Model):
    """Company model - core entity for multi-company support"""
    name = models.CharField(max_length=200)
    legal_name = models.CharField(max_length=200, blank=True)
    tin_number = models.CharField(
        max_length=50, 
        unique=True, 
        verbose_name="TIN Number",
        help_text="Tax Identification Number"
    )
    registration_number = models.CharField(
        max_length=50, 
        blank=True, 
        verbose_name="Registration Number",
        help_text="Business registration number"
    )
    address = models.TextField()
    city = models.CharField(max_length=100, blank=True, default="Addis Ababa")
    country = models.CharField(max_length=100, blank=True, default="Ethiopia")
    phone = models.CharField(max_length=20)
    email = models.EmailField()
    website = models.URLField(blank=True, verbose_name="Website")
    logo = models.ImageField(upload_to='company/logo/', blank=True, null=True)
    
    # Financial year settings
    fiscal_year_start = models.DateField(
        null=True, 
        blank=True,
        help_text="Start date of fiscal year (e.g., July 1)"
    )
    fiscal_year_end = models.DateField(
        null=True, 
        blank=True,
        help_text="End date of fiscal year (e.g., June 30)"
    )
    
    # Currency settings
    base_currency = models.CharField(
        max_length=3, 
        default="ETB",
        help_text="Base currency code (ETB, USD, etc.)"
    )
    
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='created_companies'
    )

    class Meta:
        verbose_name = "Company"
        verbose_name_plural = "Companies"
        ordering = ['name']
        indexes = [
            models.Index(fields=['tin_number']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        return self.name

    @property
    def branches_count(self):
        """Get number of active branches"""
        return self.branches.filter(is_active=True).count()


class Branch(CompanyModel):
    """Branch/Division of a company"""
    company = models.ForeignKey(
        Company, 
        on_delete=models.CASCADE, 
        related_name='branches'
    )
    name = models.CharField(max_length=150)
    code = models.CharField(max_length=20, unique=True)
    address = models.TextField()
    city = models.CharField(max_length=100, blank=True, default="Addis Ababa")
    country = models.CharField(max_length=100, blank=True, default="Ethiopia")
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    is_main = models.BooleanField(
        default=False,
        help_text="Is this the main/headquarters branch?"
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Branch"
        verbose_name_plural = "Branches"
        ordering = ['company', 'name']
        unique_together = ['company', 'code']
        indexes = [
            models.Index(fields=['code']),
            models.Index(fields=['is_main', 'is_active']),
        ]

    def __str__(self):
        return f"{self.name} ({self.code})"

    def save(self, *args, **kwargs):
        # Ensure only one main branch per company
        if self.is_main:
            Branch.objects.filter(company=self.company, is_main=True).exclude(pk=self.pk).update(is_main=False)
        super().save(*args, **kwargs)


class Department(CompanyModel):
    """Department within a company/branch"""
    company = models.ForeignKey(
        Company, 
        on_delete=models.CASCADE, 
        related_name='departments'
    )
    branch = models.ForeignKey(
        Branch, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='departments'
    )
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20, unique=True)
    description = models.TextField(blank=True)
    manager = models.ForeignKey(
        'UserProfile',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='managed_departments'
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Department"
        verbose_name_plural = "Departments"
        ordering = ['company', 'name']
        unique_together = ['company', 'code']

    def __str__(self):
        return f"{self.name} - {self.company.name}"


class UserProfile(CompanyModel):
    """Extended user profile with company and role information"""
    
    ROLE_CHOICES = [
        ('admin', 'System Administrator'),
        ('manager', 'General Manager'),
        ('production', 'Production Manager'),
        ('production_staff', 'Production Staff'),
        ('inventory', 'Inventory Manager'),
        ('inventory_staff', 'Inventory Staff'),
        ('finance', 'Finance Manager'),
        ('finance_staff', 'Finance Staff'),
        ('purchasing', 'Purchasing Manager'),
        ('purchasing_staff', 'Purchasing Staff'),
        ('sales', 'Sales Manager'),
        ('sales_staff', 'Sales Staff'),
        ('quality', 'Quality Assurance'),
        ('hr', 'Human Resources'),
        ('viewer', 'Read-Only Viewer'),
    ]

    user = models.OneToOneField(
        User, 
        on_delete=models.CASCADE, 
        related_name='profile',
        limit_choices_to={'is_active': True}
    )
    company = models.ForeignKey(
        Company, 
        on_delete=models.PROTECT,
        related_name='user_profiles',
        limit_choices_to={'is_active': True}
    )
    branch = models.ForeignKey(
        Branch, 
        on_delete=models.PROTECT, 
        null=True, 
        blank=True,
        related_name='user_profiles',
        limit_choices_to={'is_active': True}
    )
    department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='employees'
    )
    employee_id = models.CharField(
        max_length=50, 
        blank=True,
        unique=True,
        help_text="Unique employee identification number"
    )
    job_title = models.CharField(max_length=100, blank=True)
    role = models.CharField(max_length=50, choices=ROLE_CHOICES, default='viewer')
    
    # Contact information
    phone = models.CharField(max_length=20, blank=True)
    mobile = models.CharField(max_length=20, blank=True)
    emergency_contact = models.CharField(max_length=100, blank=True)
    emergency_phone = models.CharField(max_length=20, blank=True)
    
    # Personal information
    date_of_birth = models.DateField(null=True, blank=True)
    hire_date = models.DateField(null=True, blank=True)
    termination_date = models.DateField(null=True, blank=True)
    
    # Address
    address = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, blank=True, default="Ethiopia")
    
    # Status
    is_active = models.BooleanField(default=True)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='created_profiles'
    )

    class Meta:
        verbose_name = "User Profile"
        verbose_name_plural = "User Profiles"
        ordering = ['user__username']
        indexes = [
            models.Index(fields=['employee_id']),
            models.Index(fields=['role', 'is_active']),
        ]

    def __str__(self):
        full_name = self.user.get_full_name()
        if full_name:
            return f"{full_name} - {self.company.name} ({self.get_role_display()})"
        return f"{self.user.username} - {self.company.name} ({self.get_role_display()})"

    @property
    def full_name(self):
        return self.user.get_full_name() or self.user.username

    @property
    def email(self):
        return self.user.email

    @property
    def is_manager(self):
        """Check if user has managerial role"""
        managerial_roles = ['admin', 'manager', 'production', 'inventory', 'finance', 'purchasing', 'sales']
        return self.role in managerial_roles

    def save(self, *args, **kwargs):
        # Auto-generate employee_id if not provided
        if not self.employee_id:
            prefix = self.company.name[:3].upper()
            count = UserProfile.objects.filter(company=self.company).count() + 1
            self.employee_id = f"{prefix}{count:05d}"
        super().save(*args, **kwargs)


class Customer(CompanyModel):
    """Customer model for sales and receivables"""
    company = models.ForeignKey(
        Company, 
        on_delete=models.PROTECT, 
        related_name='customers'
    )
    customer_type = models.CharField(
        max_length=20,
        choices=[
            ('individual', 'Individual'),
            ('company', 'Company'),
            ('government', 'Government'),
            ('ngo', 'Non-Government Organization'),
        ],
        default='company'
    )
    name = models.CharField(max_length=200)
    tin = models.CharField(
        max_length=50, 
        blank=True, 
        verbose_name="TIN Number",
        help_text="Tax Identification Number"
    )
    registration_number = models.CharField(max_length=50, blank=True)
    
    # Contact information
    contact_person = models.CharField(max_length=100, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    mobile = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    website = models.URLField(blank=True)
    
    # Address
    address = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True, default="Addis Ababa")
    country = models.CharField(max_length=100, blank=True, default="Ethiopia")
    
    # Financial
    credit_limit = models.DecimalField(
        max_digits=15, 
        decimal_places=2, 
        default=0,
        help_text="Maximum credit allowed (0 = no limit)"
    )
    payment_terms = models.PositiveIntegerField(
        default=30,
        help_text="Payment terms in days"
    )
    currency = models.CharField(max_length=3, default="ETB")
    
    # Status
    is_active = models.BooleanField(default=True)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='created_customers'
    )

    class Meta:
        verbose_name = "Customer"
        verbose_name_plural = "Customers"
        ordering = ['name']
        indexes = [
            models.Index(fields=['tin']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        return self.name

    @property
    def total_invoiced(self):
        """Get total amount invoiced to this customer"""
        from apps.accounting.models import SalesInvoice
        return SalesInvoice.objects.filter(
            customer=self,
            status__in=['posted', 'paid']
        ).aggregate(total=models.Sum('total_amount'))['total'] or 0

    @property
    def outstanding_balance(self):
        """Get outstanding balance for this customer"""
        from apps.accounting.models import SalesInvoice
        return SalesInvoice.objects.filter(
            customer=self,
            status__in=['posted', 'partial', 'overdue']
        ).aggregate(total=models.Sum('remaining_amount'))['total'] or 0