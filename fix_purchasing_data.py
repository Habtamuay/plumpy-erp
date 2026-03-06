import sqlite3
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'plumpy_erp.settings')
django.setup()

from apps.core.models import Unit, Item
from apps.purchasing.models import PurchaseOrderLine, PurchaseRequisitionLine

def fix_purchasing_data():
    """Fix the data to match the new foreign key structure"""
    
    print("Starting data fix...")
    
    # Step 1: Create default units
    print("\n1. Creating default units...")
    default_units = [
        {'name': 'Pieces', 'abbreviation': 'Pcs'},
        {'name': 'Kilogram', 'abbreviation': 'Kg'},
        {'name': 'Liter', 'abbreviation': 'L'},
        {'name': 'Meter', 'abbreviation': 'm'},
        {'name': 'Box', 'abbreviation': 'Box'},
        {'name': 'Pack', 'abbreviation': 'Pack'},
        {'name': 'Dozen', 'abbreviation': 'Doz'},
        {'name': 'Set', 'abbreviation': 'Set'},
    ]
    
    unit_map = {}
    for unit_data in default_units:
        unit, created = Unit.objects.get_or_create(
            abbreviation=unit_data['abbreviation'],
            defaults={'name': unit_data['name']}
        )
        unit_map[unit_data['abbreviation']] = unit.id
        print(f"  {'Created' if created else 'Found'}: {unit.abbreviation} (ID: {unit.id})")
    
    # Step 2: Create a default item
    print("\n2. Creating default item...")
    default_item, created = Item.objects.get_or_create(
        code='DEFAULT',
        defaults={
            'name': 'Default Item',
            'description': 'Auto-created default item for migration'
        }
    )
    print(f"  {'Created' if created else 'Found'}: {default_item.code} (ID: {default_item.id})")
    
    # Step 3: Connect directly to SQLite to update the data
    print("\n3. Updating PurchaseOrderLine data...")
    conn = sqlite3.connect('db.sqlite3')
    cursor = conn.cursor()
    
    # First, check what columns exist
    cursor.execute("PRAGMA table_info(purchasing_purchaseorderline)")
    columns = [col[1] for col in cursor.fetchall()]
    print(f"  Available columns: {columns}")
    
    # Check if we need to add the new columns first
    if 'item_id' not in columns:
        print("  Adding item_id column...")
        cursor.execute("ALTER TABLE purchasing_purchaseorderline ADD COLUMN item_id INTEGER REFERENCES core_item(id)")
    if 'unit_id' not in columns:
        print("  Adding unit_id column...")
        cursor.execute("ALTER TABLE purchasing_purchaseorderline ADD COLUMN unit_id INTEGER REFERENCES core_unit(id)")
    
    conn.commit()
    
    # Now get the data
    cursor.execute("SELECT id, item, unit FROM purchasing_purchaseorderline")
    rows = cursor.fetchall()
    print(f"  Found {len(rows)} rows to process")
    
    for row in rows:
        line_id, old_item, old_unit = row
        print(f"    Processing line {line_id}: item='{old_item}', unit='{old_unit}'")
        
        # Map unit
        unit_id = None
        if old_unit and old_unit in unit_map:
            unit_id = unit_map[old_unit]
        else:
            # Default to Pcs
            unit_id = unit_map.get('Pcs', 1)
        
        # For item, we need to create a mapping
        # Since we don't have actual Item objects, we'll use the default
        item_id = default_item.id
        
        # Update the record
        cursor.execute("""
            UPDATE purchasing_purchaseorderline 
            SET item_id = ?, unit_id = ? 
            WHERE id = ?
        """, (item_id, unit_id, line_id))
    
    # Step 4: Update PurchaseRequisitionLine
    print("\n4. Updating PurchaseRequisitionLine data...")
    
    # Check PurchaseRequisitionLine columns
    cursor.execute("PRAGMA table_info(purchasing_purchaserequisitionline)")
    columns = [col[1] for col in cursor.fetchall()]
    print(f"  Available columns: {columns}")
    
    # Add columns if needed
    if 'item_id' not in columns:
        print("  Adding item_id column...")
        cursor.execute("ALTER TABLE purchasing_purchaserequisitionline ADD COLUMN item_id INTEGER REFERENCES core_item(id)")
    if 'unit_id' not in columns:
        print("  Adding unit_id column...")
        cursor.execute("ALTER TABLE purchasing_purchaserequisitionline ADD COLUMN unit_id INTEGER REFERENCES core_unit(id)")
    
    conn.commit()
    
    cursor.execute("SELECT id, item, unit FROM purchasing_purchaserequisitionline")
    rows = cursor.fetchall()
    print(f"  Found {len(rows)} rows to process")
    
    for row in rows:
        line_id, old_item, old_unit = row
        print(f"    Processing line {line_id}: item='{old_item}', unit='{old_unit}'")
        
        # Map unit
        unit_id = None
        if old_unit and old_unit in unit_map:
            unit_id = unit_map[old_unit]
        else:
            unit_id = unit_map.get('Pcs', 1)
        
        # Use default item
        item_id = default_item.id
        
        # Update the record
        cursor.execute("""
            UPDATE purchasing_purchaserequisitionline 
            SET item_id = ?, unit_id = ? 
            WHERE id = ?
        """, (item_id, unit_id, line_id))
    
    conn.commit()
    conn.close()
    
    print("\n5. Data fix completed!")
    print("\nNow you can run: python manage.py migrate purchasing 0006")

if __name__ == '__main__':
    fix_purchasing_data()