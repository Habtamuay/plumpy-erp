from rest_framework import serializers
from .models import (
    ReportCategory,
    ReportTemplate,
    ReportRequest,
    ScheduledReport,
    DashboardWidget,
)
from django.contrib.auth import get_user_model

User = get_user_model()


class ReportCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ReportCategory
        fields = [
            'id',
            'name',
            'icon',
            'description',
            'display_order',
            'is_active',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at']


class ReportTemplateListSerializer(serializers.ModelSerializer):
    """Used for list views – lighter version"""
    category_name = serializers.CharField(source='category.name', read_only=True)

    class Meta:
        model = ReportTemplate
        fields = [
            'id',
            'name',
            'slug',
            'report_type',
            'format',
            'category',
            'category_name',
            'icon',
            'color',
            'is_system',
            'is_active',
        ]


class ReportTemplateDetailSerializer(serializers.ModelSerializer):
    """Full detail serializer – used for retrieve/update"""
    category = ReportCategorySerializer(read_only=True)
    category_id = serializers.PrimaryKeyRelatedField(
        queryset=ReportCategory.objects.all(),
        source='category',
        write_only=True,
        required=False,
        allow_null=True
    )
    created_by_username = serializers.CharField(source='created_by.username', read_only=True)

    class Meta:
        model = ReportTemplate
        fields = [
            'id',
            'name',
            'slug',
            'description',
            'report_type',
            'format',
            'category',
            'category_id',
            'template_file',
            'query_config',
            'icon',
            'color',
            'is_system',
            'is_active',
            'created_by',
            'created_by_username',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'is_system',
            'created_by',
            'created_at',
            'updated_at',
            'created_by_username',
        ]

    def create(self, validated_data):
        # Automatically set created_by to current user
        validated_data['created_by'] = self.context['request'].user
        return super().create(validated_data)


class ReportRequestListSerializer(serializers.ModelSerializer):
    user_username = serializers.CharField(source='user.username', read_only=True)
    template_name = serializers.CharField(source='template.name', read_only=True, allow_null=True)

    class Meta:
        model = ReportRequest
        fields = [
            'id',
            'report_type',
            'format',
            'status',
            'user',
            'user_username',
            'template',
            'template_name',
            'created_at',
            'completed_at',
            'file',
        ]
        read_only_fields = [
            'id',
            'user',
            'user_username',
            'created_at',
            'completed_at',
            'file',
        ]


class ReportRequestCreateSerializer(serializers.ModelSerializer):
    """Used for creating new report requests"""
    class Meta:
        model = ReportRequest
        fields = [
            'report_type',
            'format',
            'parameters',
            'template',  # optional – if linked to a template
        ]

    def validate(self, data):
        # Optional: add business validation
        if not data.get('report_type') and not data.get('template'):
            raise serializers.ValidationError(
                "Either report_type or template must be provided."
            )
        return data

    def create(self, validated_data):
        validated_data['user'] = self.context['request'].user
        # If template is provided, copy report_type/format if not set
        if template := validated_data.get('template'):
            if not validated_data.get('report_type'):
                validated_data['report_type'] = template.report_type
            if not validated_data.get('format'):
                validated_data['format'] = template.format
        return super().create(validated_data)


class ReportRequestDetailSerializer(serializers.ModelSerializer):
    user_username = serializers.CharField(source='user.username', read_only=True)
    template_name = serializers.CharField(source='template.name', read_only=True, allow_null=True)

    class Meta:
        model = ReportRequest
        fields = [
            'id',
            'report_type',
            'format',
            'parameters',
            'status',
            'task_id',
            'file',
            'error_message',
            'user',
            'user_username',
            'template',
            'template_name',
            'created_at',
            'completed_at',
        ]
        read_only_fields = [
            'id',
            'status',
            'task_id',
            'file',
            'error_message',
            'created_at',
            'completed_at',
            'user',
            'user_username',
        ]


class ScheduledReportSerializer(serializers.ModelSerializer):
    report_name = serializers.CharField(source='report.name', read_only=True)
    created_by_username = serializers.CharField(source='created_by.username', read_only=True)

    class Meta:
        model = ScheduledReport
        fields = [
            'id',
            'name',
            'description',
            'report',
            'report_name',
            'schedule_type',
            'hour',
            'minute',
            'day_of_month',
            'day_of_week',
            'custom_cron',
            'recipients',
            'email_subject',
            'email_body',
            'format',
            'include_charts',
            'include_tables',
            'is_active',
            'last_run',
            'next_run',
            'created_by',
            'created_by_username',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'last_run',
            'next_run',
            'created_by',
            'created_by_username',
            'created_at',
            'updated_at',
        ]

    def validate(self, data):
        if data['schedule_type'] == 'custom' and not data.get('custom_cron'):
            raise serializers.ValidationError(
                {"custom_cron": "This field is required when schedule_type is 'custom'."}
            )
        return data


class DashboardWidgetSerializer(serializers.ModelSerializer):
    report_name = serializers.CharField(source='report.name', read_only=True, allow_null=True)
    user_username = serializers.CharField(source='user.username', read_only=True)

    class Meta:
        model = DashboardWidget
        fields = [
            'id',
            'title',
            'widget_type',
            'report',
            'report_name',
            'size',
            'position',
            'config',
            'is_visible',
            'user',
            'user_username',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'user',
            'user_username',
            'created_at',
            'updated_at',
        ]


class DashboardWidgetCreateUpdateSerializer(serializers.ModelSerializer):
    """Used for create/update – user is set automatically"""

    class Meta:
        model = DashboardWidget
        fields = [
            'title',
            'widget_type',
            'report',
            'size',
            'position',
            'config',
            'is_visible',
        ]

    def create(self, validated_data):
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)