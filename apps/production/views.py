from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Sum, F, Q, Count
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.views.decorators.http import require_POST
from decimal import Decimal
import json

from .models import ProductionRun, BOM, InventoryMovement, ProductionCostVariance
from apps.core.models import Item
from .forms import StartProductionRunForm, CompleteProductionRunForm, MaterialTransferForm, ProductionSearchForm


# ────────────────────────────────────────────────
# Dashboard
# ────────────────────────────────────────────────

@login_required
def dashboard(request):
    """Main production dashboard with key metrics and summaries"""
    company_id = request.session.get('current_company_id')
    company_name = request.session.get('current_company_name')
    if not company_id:
        messages.warning(request, 'Please select a company first.')
        return redirect('core:home')

    today = timezone.now().date()
    
    # Stock alerts
    low_stock = Item.objects.filter(
        Q(company_id=company_id) | Q(company__isnull=True),
        current_stock__lte=F('minimum_stock'),
        current_stock__gt=0,
        is_active=True
    ).select_related('unit').order_by('current_stock')[:10]

    out_of_stock = Item.objects.filter(
        Q(company_id=company_id) | Q(company__isnull=True),
        current_stock=0,
        is_active=True
    ).select_related('unit')[:5]

    # BOM statistics
    active_boms = BOM.objects.filter(
        is_active=True,
        company_id=company_id
    ).select_related('product').order_by('-effective_from')[:10]
    total_boms = BOM.objects.filter(is_active=True, company_id=company_id).count()

    # Production runs
    recent_runs = ProductionRun.objects.filter(
        company_id=company_id
    ).select_related('product', 'bom').order_by('-start_date')[:10]
    planned_runs = ProductionRun.objects.filter(
        status='planned',
        company_id=company_id
    ).select_related('product').order_by('start_date')[:5]
    in_progress = ProductionRun.objects.filter(
        status='in_progress',
        company_id=company_id
    ).select_related('product').order_by('-start_date')[:5]
    completed_today = ProductionRun.objects.filter(
        status='completed',
        company_id=company_id,
        end_date__date=today
    ).count()

    # Recent stock movements
    recent_movements = InventoryMovement.objects.select_related(
        'item', 'production_run', 'created_by'
    ).filter(
        Q(production_run__company_id=company_id) | Q(item__company_id=company_id)
    ).order_by('-created_at')[:15]

    # Statistics
    stats = {
        'total_items': Item.objects.filter(
            Q(company_id=company_id) | Q(company__isnull=True),
            is_active=True
        ).count(),
        'total_boms': total_boms,
        'total_completed': ProductionRun.objects.filter(status='completed', company_id=company_id).count(),
        'total_planned': ProductionRun.objects.filter(status='planned', company_id=company_id).count(),
        'total_in_progress': ProductionRun.objects.filter(status='in_progress', company_id=company_id).count(),
        'completed_today': completed_today,
        'total_movements': InventoryMovement.objects.filter(
            Q(production_run__company_id=company_id) | Q(item__company_id=company_id)
        ).count(),
    }

    context = {
        'current_company_name': company_name,
        'low_stock': low_stock,
        'out_of_stock': out_of_stock,
        'active_boms': active_boms,
        'recent_runs': recent_runs,
        'planned_runs': planned_runs,
        'in_progress': in_progress,
        'in_progress_runs': in_progress,
        'recent_movements': recent_movements,
        'stats': stats,
        'today': today,
    }

    return render(request, 'production/dashboard.html', context)


# ────────────────────────────────────────────────
# Production Run Views
# ────────────────────────────────────────────────

@login_required
def production_run_list(request):
    """List all production runs with filtering"""
    runs = ProductionRun.objects.select_related('bom', 'product', 'created_by').order_by('-start_date')
    company_id = request.session.get('current_company_id')
    if company_id:
        # Include legacy records with no company set, so historical runs remain visible.
        runs = runs.filter(Q(company_id=company_id) | Q(company__isnull=True))
    
    # Apply filters
    form = ProductionSearchForm(request.GET)
    if form.is_valid():
        if form.cleaned_data.get('search'):
            search = form.cleaned_data['search']
            runs = runs.filter(
                Q(product__code__icontains=search) |
                Q(product__name__icontains=search) |
                Q(notes__icontains=search)
            )
        if form.cleaned_data.get('status'):
            runs = runs.filter(status=form.cleaned_data['status'])
        if form.cleaned_data.get('date_from'):
            runs = runs.filter(start_date__date__gte=form.cleaned_data['date_from'])
        if form.cleaned_data.get('date_to'):
            runs = runs.filter(start_date__date__lte=form.cleaned_data['date_to'])
        if form.cleaned_data.get('product'):
            runs = runs.filter(product=form.cleaned_data['product'])
    
    # Pagination could be added here
    
    context = {
        'runs': runs,
        'form': form,
        'status_choices': ProductionRun.STATUS_CHOICES,
        'products': Item.objects.filter(category='finished', is_active=True),
        'current_company_name': request.session.get('current_company_name'),
    }
    return render(request, 'production/production_run_list.html', context)


@login_required
def edit_production_run(request, pk):
    """
    Edit a production run (planned/in-progress only).
    """
    run = get_object_or_404(ProductionRun.objects.select_related('bom', 'product'), pk=pk)
    company_id = request.session.get('current_company_id')
    if company_id and run.company_id and run.company_id != company_id:
        messages.error(request, "This run does not belong to the selected company.")
        return redirect('production:production_run_list')

    if run.status in ['completed', 'cancelled', 'failed']:
        messages.error(request, f"Cannot edit a run with status '{run.get_status_display()}'.")
        return redirect('production:production_run_detail', pk=run.pk)

    if request.method == 'POST':
        form = StartProductionRunForm(request.POST, instance=run, user=request.user)
        if form.is_valid():
            updated_run = form.save(commit=False)
            # Ensure company/product consistency
            if run.company_id and not updated_run.company_id:
                updated_run.company_id = run.company_id
            if updated_run.bom and updated_run.bom.product:
                updated_run.product = updated_run.bom.product
            updated_run.save()
            messages.success(request, f'Production Run #{updated_run.id} updated successfully.')
            return redirect('production:production_run_detail', pk=updated_run.pk)
    else:
        form = StartProductionRunForm(instance=run, user=request.user)

    context = {
        'form': form,
        'run': run,
        'is_edit': True,
    }
    return render(request, 'production/start_run.html', context)


@login_required
@require_POST
def start_existing_run(request, pk):
    """
    Move a planned run to in-progress.
    """
    run = get_object_or_404(ProductionRun, pk=pk)
    company_id = request.session.get('current_company_id')
    if company_id and run.company_id and run.company_id != company_id:
        messages.error(request, "This run does not belong to the selected company.")
        return redirect('production:production_run_list')

    try:
        run.start()
        messages.success(request, f"Run #{run.id} moved to In Progress.")
    except ValidationError as e:
        messages.error(request, f"Could not start run: {e}")
    return redirect('production:production_run_detail', pk=run.pk)


@login_required
def production_run_detail(request, pk):
    """View detailed information about a production run"""
    run = get_object_or_404(
        ProductionRun.objects.select_related('bom', 'product', 'created_by'),
        pk=pk
    )
    
    # Get material requirements
    material_requirements = run.required_components
    
    # Get movements for this run
    movements = run.movements.select_related('item', 'from_warehouse', 'to_warehouse').order_by('-created_at')
    
    # Get cost variance if exists
    try:
        variance = run.cost_variance
    except ProductionCostVariance.DoesNotExist:
        variance = None
    
    context = {
        'run': run,
        'material_requirements': material_requirements,
        'movements': movements,
        'variance': variance,
        'today': timezone.now().date(),
    }
    return render(request, 'production/production_run_detail.html', context)


@login_required
def start_production_run(request):
    """Start a new production run"""
    # remove stale/invalid material requirements from prior attempts
    if 'material_requirements' in request.session:
        try:
            json.dumps(request.session['material_requirements'])
        except TypeError:
            # previous value contained non-serializable data (e.g. Decimal)
            del request.session['material_requirements']
    
    if request.method == 'POST':
        form = StartProductionRunForm(request.POST, user=request.user)
        if form.is_valid():
            try:
                run = form.save(commit=False)
                run.created_by = request.user
                # Always scope new runs to the selected company.
                company_id = request.session.get('current_company_id')
                if company_id:
                    run.company_id = company_id
                run.save()
                
                # Store material requirements in session for display
                if hasattr(form, 'material_requirements'):
                    # Convert components to serializable dicts before storing in session
                    serializable = []
                    for req in form.material_requirements:
                        # Helper to normalize numbers so JSON can handle them
                        def norm(val):
                            if val is None:
                                return None
                            if isinstance(val, Decimal):
                                return float(val)
                            return val
                        serializable.append({
                            'component_id': req['component'].id if hasattr(req['component'], 'id') else None,
                            'component_name': str(req['component']),
                            'required': norm(req.get('required')),
                            'required_with_wastage': norm(req.get('required_with_wastage')),
                            'unit': req.get('unit').abbreviation if req.get('unit') else None,
                            'available': norm(req.get('available')),
                            'wastage': norm(req.get('wastage')),
                        })
                    request.session['material_requirements'] = serializable
                
                messages.success(
                    request, 
                    f'Production Run #{run.id} created successfully. '
                    f'Estimated cost: {form.cleaned_data.get("estimated_cost", 0):,.2f} ETB'
                )
                return redirect('production:production_run_detail', pk=run.pk)
            except Exception as e:
                messages.error(request, f'Error creating production run: {e}')
    else:
        form = StartProductionRunForm(user=request.user)
    
    # Get BOM choices for dropdown
    boms = BOM.objects.filter(is_active=True).select_related('product')
    
    context = {
        'form': form,
        'boms': boms,
        'today': timezone.now().date(),
    }
    return render(request, 'production/start_run.html', context)


@login_required
def complete_production_run(request, pk):
    """Complete a production run and update inventory"""
    run = get_object_or_404(ProductionRun, pk=pk)

    if run.status != 'in_progress':
        messages.error(request, "This run is not in progress and cannot be completed.")
        return redirect('production:production_run_detail', pk=pk)

    if request.method == 'POST':
        form = CompleteProductionRunForm(request.POST, production_run=run)
        if form.is_valid():
            try:
                actual_qty = form.cleaned_data['actual_quantity']
                waste_qty = form.cleaned_data.get('waste_quantity', 0)
                completion_date = form.cleaned_data.get('completion_date')
                notes = form.cleaned_data.get('notes', '')
                
                # Update run notes if provided
                if notes:
                    run.notes = (run.notes or '') + f"\nCompletion notes: {notes}"
                
                # Complete the run
                run.complete(actual_qty=actual_qty, waste_qty=waste_qty)
                
                # Update completion date if different
                if completion_date and completion_date != run.end_date.date():
                    run.end_date = timezone.datetime.combine(completion_date, timezone.now().time())
                    run.save()
                
                messages.success(
                    request, 
                    f'Run #{run.id} completed successfully. '
                    f'Yield: {run.yield_percentage:.1f}%'
                )
                
                # Check if variance record was created
                if hasattr(run, 'cost_variance'):
                    variance = run.cost_variance
                    if abs(variance.variance_percentage) > 10:
                        messages.warning(
                            request,
                            f'High cost variance detected: {variance.variance_percentage:+.1f}%'
                        )
                
            except ValidationError as e:
                messages.error(request, f"Failed to complete run: {e}")
            except Exception as e:
                messages.error(request, f"Unexpected error: {e}")
            
            return redirect('production:production_run_detail', pk=pk)
    else:
        form = CompleteProductionRunForm(
            initial={
                'actual_quantity': run.planned_quantity,
                'completion_date': timezone.now().date()
            },
            production_run=run
        )

    # Get material requirements for display
    material_requirements = run.required_components
    
    context = {
        'run': run,
        'form': form,
        'material_requirements': material_requirements,
    }
    return render(request, 'production/complete_run.html', context)


@login_required
def cancel_production_run(request, pk):
    """Cancel a production run"""
    run = get_object_or_404(ProductionRun, pk=pk)
    
    if run.status in ['completed', 'cancelled']:
        messages.error(request, f"Cannot cancel run with status '{run.status}'")
        return redirect('production:production_run_detail', pk=pk)
    
    if request.method == 'POST':
        reason = request.POST.get('reason', '')
        try:
            run.cancel()
            if reason:
                run.notes = (run.notes or '') + f"\nCancellation reason: {reason}"
                run.save()
            messages.success(request, f'Run #{run.id} cancelled successfully.')
            return redirect('production:production_run_list')
        except ValidationError as e:
            messages.error(request, f'Error cancelling run: {e}')
    
    context = {
        'run': run,
    }
    return render(request, 'production/cancel_run.html', context)


# ────────────────────────────────────────────────
# BOM Views
# ────────────────────────────────────────────────

@login_required
def bom_list(request):
    """List all BOMs"""
    boms = BOM.objects.filter(is_active=True).select_related('product').prefetch_related('lines')
    
    # Add component count
    for bom in boms:
        bom.component_count = bom.lines.count()
    
    context = {
        'boms': boms,
    }
    return render(request, 'production/bom_list.html', context)


@login_required
def bom_detail(request, pk):
    """View BOM details"""
    bom = get_object_or_404(
        BOM.objects.select_related('product').prefetch_related('lines__component', 'lines__unit'),
        pk=pk
    )
    
    # Calculate total cost
    total_cost = bom.total_material_cost_per_base
    
    # Create a list of dictionaries for lines with additional calculated fields
    lines_data = []
    for line in bom.lines.all().order_by('sequence'):
        # Calculate cost per base
        cost_per_base = line.quantity_per_base * (line.component.unit_cost or 0)
        
        # Calculate percentage
        if total_cost and total_cost > 0:
            cost_percentage = (cost_per_base / total_cost) * 100
        else:
            cost_percentage = 0
        
        lines_data.append({
            'sequence': line.sequence,
            'component': line.component,
            'unit': line.unit,
            'quantity_per_base': line.quantity_per_base,
            'wastage_percentage': line.wastage_percentage,
            'is_critical': line.is_critical,
            'notes': line.notes,
            'cost_per_base': cost_per_base,
            'cost_percentage': cost_percentage,
        })
    
    context = {
        'bom': bom,
        'lines': lines_data,  # Use the list of dictionaries instead of the queryset
        'total_cost': total_cost,
    }
    
    return render(request, 'production/bom_detail.html', context)


# ────────────────────────────────────────────────
# Inventory Movement Views
# ────────────────────────────────────────────────

@login_required
def movement_list(request):
    """List all inventory movements"""
    movements = InventoryMovement.objects.select_related(
        'item', 'production_run', 'created_by', 'from_warehouse', 'to_warehouse'
    ).order_by('-created_at')
    
    # Filter by type
    movement_type = request.GET.get('type')
    if movement_type:
        movements = movements.filter(movement_type=movement_type)
    
    # Filter by date
    date_from = request.GET.get('from')
    date_to = request.GET.get('to')
    if date_from and date_to:
        movements = movements.filter(created_at__date__range=[date_from, date_to])
    
    context = {
        'movements': movements[:100],  # Limit to 100 for performance
        'movement_types': InventoryMovement.MOVEMENT_TYPES,
    }
    return render(request, 'production/movement_list.html', context)


@login_required
def movement_detail(request, pk):
    """View movement details"""
    movement = get_object_or_404(
        InventoryMovement.objects.select_related(
            'item', 'production_run', 'created_by', 'from_warehouse', 'to_warehouse'
        ),
        pk=pk
    )
    
    context = {
        'movement': movement,
    }
    return render(request, 'production/movement_detail.html', context)


# ────────────────────────────────────────────────
# Cost Variance Reports
# ────────────────────────────────────────────────

@login_required
def cost_variance_report(request):
    """Comprehensive cost variance report"""
    # Get completed runs
    runs = ProductionRun.objects.filter(
        status='completed'
    ).select_related('product', 'bom').prefetch_related(
        'movements', 'bom__lines__component'
    ).order_by('-end_date')[:50]

    # Summary aggregates
    total_standard = runs.aggregate(total=Sum('standard_material_cost'))['total'] or Decimal('0.00')
    total_actual = runs.aggregate(total=Sum('actual_material_cost'))['total'] or Decimal('0.00')
    total_variance = total_actual - total_standard
    variance_percent = (total_variance / total_standard * 100) if total_standard > 0 else Decimal('0.00')

    # Per-run, per-component variance
    detailed_variances = []
    for run in runs:
        if not run.bom or not run.bom.lines.exists():
            continue

        # Standard cost per component from BOM
        std_per_component = {}
        for line in run.bom.lines.select_related('component', 'unit'):
            qty_with_waste = line.quantity_per_kg * (run.actual_quantity or run.planned_quantity) * (1 + line.wastage_percentage / 100)
            std_cost = qty_with_waste * (line.component.unit_cost or 0)
            std_per_component[line.component_id] = {
                'component': line.component,
                'std_qty': qty_with_waste,
                'std_cost': std_cost,
                'unit': line.unit.abbreviation,
            }

        # Actual cost per component from InventoryMovement
        actual_movements = InventoryMovement.objects.filter(
            production_run=run,
            movement_type='out_production'
        ).values('item_id').annotate(
            actual_qty=Sum('quantity')
        )

        actual_per_component = {}
        for m in actual_movements:
            item_id = m['item_id']
            actual_qty = abs(m['actual_qty'])
            try:
                item = Item.objects.get(id=item_id)
                actual_cost = actual_qty * (item.unit_cost or 0)
                actual_per_component[item_id] = {
                    'actual_qty': actual_qty,
                    'actual_cost': actual_cost,
                    'item': item,
                }
            except Item.DoesNotExist:
                continue

        # Build component variance list
        component_variances = []
        for comp_id, std in std_per_component.items():
            actual = actual_per_component.get(comp_id, {
                'actual_qty': Decimal('0.00'),
                'actual_cost': Decimal('0.00')
            })
            variance = actual['actual_cost'] - std['std_cost']
            variance_pct = (variance / std['std_cost'] * 100) if std['std_cost'] > 0 else Decimal('0.00')
            
            component_variances.append({
                'component': std['component'],
                'std_qty': std['std_qty'],
                'std_cost': std['std_cost'],
                'actual_qty': actual['actual_qty'],
                'actual_cost': actual['actual_cost'],
                'variance': variance,
                'variance_percent': variance_pct,
                'unit': std['unit'],
            })

        # Sort by largest variance magnitude
        component_variances.sort(key=lambda x: abs(x['variance']), reverse=True)

        # Get cost variance model if exists
        try:
            cost_variance = run.cost_variance
        except ProductionCostVariance.DoesNotExist:
            cost_variance = None

        detailed_variances.append({
            'run': run,
            'component_variances': component_variances[:10],  # Top 10 variances
            'cost_variance': cost_variance,
        })

    context = {
        'runs': runs,
        'total_standard': total_standard,
        'total_actual': total_actual,
        'total_variance': total_variance,
        'variance_percent': variance_percent,
        'detailed_variances': detailed_variances,
        'today': timezone.now().date(),
    }
    return render(request, 'production/cost_variance_report.html', context)


@login_required
def production_cost_variance_report(request):
    """Alternative variance report using ProductionCostVariance model"""
    variances = ProductionCostVariance.objects.select_related(
        'production_run__product'
    ).order_by('-calculated_at')[:50]

    context = {
        'variances': variances,
        'today': timezone.now().date(),
    }
    return render(request, 'production/cost_variance_report_simple.html', context)


# ────────────────────────────────────────────────
# AJAX Views
# ────────────────────────────────────────────────

@login_required
def ajax_bom_details(request, bom_id):
    """AJAX endpoint to get BOM details"""
    from django.http import JsonResponse
    
    bom = get_object_or_404(BOM.objects.prefetch_related('lines__component', 'lines__unit'), pk=bom_id)
    
    lines = []
    for line in bom.lines.all():
        lines.append({
            'component_code': line.component.code,
            'component_name': line.component.name,
            'quantity': float(line.quantity_per_kg),
            'unit': line.unit.abbreviation,
            'wastage': float(line.wastage_percentage),
            'available_stock': float(line.component.current_stock),
        })
    
    data = {
        'id': bom.id,
        'product': bom.product.code,
        'version': bom.version,
        'total_cost': float(bom.total_material_cost_per_base),
        'lines': lines,
    }
    
    return JsonResponse(data)
