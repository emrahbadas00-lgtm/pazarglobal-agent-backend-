"""Supabase SQL Setup Guide

Security note: Do NOT hardcode Supabase keys/tokens in scripts.
This script only opens the SQL Editor and prints the correct order.
"""

PROJECT_REF = "snovwbffwvmkgjulrtsm"
SUPABASE_URL = f"https://{PROJECT_REF}.supabase.co"

def main():
    print("\n🚀 SUPABASE SQL SETUP")
    print("="*70)
    print(f"📍 URL: {SUPABASE_URL}")
    print("="*70)
    
    print("\n⚠️  Automatic execution not possible via REST API")
    print("📋 SQL files must be run manually in Supabase SQL Editor\n")
    
    print("✅ STEP-BY-STEP GUIDE:")
    print("-"*70)
    
    print("\n1️⃣  Open SQL Editor:")
    print(f"    https://supabase.com/dashboard/project/{PROJECT_REF}/sql/new")
    
    print("\n2️⃣  Run session_management_migration.sql:")
    print("    - Open: database/session_management_migration.sql")
    print("    - Copy ALL content (Ctrl+A → Ctrl+C)")
    print("    - Paste in SQL Editor (Ctrl+V)")
    print("    - Click RUN ▶️")
    print("    - Wait for ✅ Success")
    
    print("\n3️⃣  Run supabase_rpc_functions.sql:")
    print("    - Click NEW QUERY")
    print("    - Open: database/supabase_rpc_functions.sql")
    print("    - Copy ALL content (Ctrl+A → Ctrl+C)")
    print("    - Paste in SQL Editor (Ctrl+V)")
    print("    - Click RUN ▶️")
    print("    - Wait for ✅ Success")
    
    print("\n" + "="*70)
    print("📋 AFTER SQL SETUP:")
    print("="*70)
    print("\n4️⃣  Deploy Edge Function:")
    print("    supabase functions deploy whatsapp-traffic-controller --project-ref snovwbffwvmkgjulrtsm")
    
    print("\n5️⃣  Add to Railway:")
    print("    EDGE_FUNCTION_URL=https://snovwbffwvmkgjulrtsm.supabase.co/functions/v1/whatsapp-traffic-controller")
    
    print("\n" + "="*70 + "\n")
    
    # Open browser
    import webbrowser
    print("🌐 Opening SQL Editor...")
    webbrowser.open(f"https://supabase.com/dashboard/project/{PROJECT_REF}/sql/new")

if __name__ == "__main__":
    main()
