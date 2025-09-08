#!/usr/bin/env python3
"""
Test script to check Google Sheets access and provide sharing instructions
"""

from modules.sheet_manager import SheetManager
from modules.config_manager import ConfigManager

def test_sheets_access():
    """Test access to all configured Google Sheets"""
    
    print("🔍 Testing Google Sheets Access")
    print("=" * 50)
    
    try:
        config = ConfigManager()
        sm = SheetManager(config)
        
        # Get the service account email from credentials
        sheets_config = config.get_google_sheets_config()
        print(f"📧 Service Account Email: {sm.service._http.credentials.service_account_email}")
        print()
        
        # Test each sheet
        sheet_ids = sheets_config['sheet_ids']
        
        print("📊 Testing access to editor sheets:")
        for editor, sheet_id in sheet_ids.items():
            print(f"\n🔸 Testing {editor}'s sheet ({sheet_id})...")
            try:
                # Try to get basic sheet info
                result = sm.service.spreadsheets().get(spreadsheetId=sheet_id).execute()
                title = result.get('properties', {}).get('title', 'Unknown')
                print(f"   ✅ SUCCESS: Can access '{title}'")
                
                # Try to read data
                try:
                    values = sm.service.spreadsheets().values().get(
                        spreadsheetId=sheet_id,
                        range="'AI notes'!A1:A1"
                    ).execute()
                    print(f"   ✅ SUCCESS: Can read data")
                except Exception as e:
                    print(f"   ⚠️  WARNING: Can access sheet but cannot read 'AI notes' tab: {e}")
                    
            except Exception as e:
                print(f"   ❌ ERROR: Cannot access sheet: {e}")
        
        # Test reference sheets
        print(f"\n📚 Testing reference sheets:")
        
        reference_sheets = {
            'Templates': sheets_config['templates_sheet'],
            'Support References': sheets_config['support_references_sheet'],
            'System Prompts': sheets_config['system_prompts_sheet']
        }
        
        for name, sheet_id in reference_sheets.items():
            print(f"\n🔸 Testing {name} sheet ({sheet_id})...")
            try:
                result = sm.service.spreadsheets().get(spreadsheetId=sheet_id).execute()
                title = result.get('properties', {}).get('title', 'Unknown')
                print(f"   ✅ SUCCESS: Can access '{title}'")
            except Exception as e:
                print(f"   ❌ ERROR: Cannot access sheet: {e}")
        
        print("\n" + "=" * 50)
        print("📋 NEXT STEPS:")
        print("=" * 50)
        print("If you see ❌ ERROR messages above, you need to share those sheets with the service account.")
        print()
        print("🔧 How to fix access issues:")
        print("1. Open each Google Sheet that shows an error")
        print("2. Click the 'Share' button (top right)")
        print("3. Add this email address as an Editor:")
        print(f"   📧 {sm.service._http.credentials.service_account_email}")
        print("4. Make sure 'Notify people' is unchecked (it's a service account)")
        print("5. Click 'Send'")
        print()
        print("🔄 After sharing, run this test again to verify access!")
        
    except Exception as e:
        print(f"❌ CRITICAL ERROR: {e}")
        print("\nCheck that your google_credentials.json file is valid and properly formatted.")

if __name__ == "__main__":
    test_sheets_access() 