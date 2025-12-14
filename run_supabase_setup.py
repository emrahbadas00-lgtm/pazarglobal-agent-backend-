"""
Supabase SQL Setup Script
Opens Supabase SQL Editor with instructions
"""
import webbrowser
import os

SUPABASE_URL = "https://snovwbffwvmkgjulrtsm.supabase.co"
PROJECT_ID = "snovwbffwvmkgjulrtsm"

def open_sql_editor():
    """Open Supabase SQL Editor in browser"""
    sql_editor_url = f"https://supabase.com/dashboard/project/{PROJECT_ID}/sql/new"
    print(f"\n🌐 Opening Supabase SQL Editor...")
    webbrowser.open(sql_editor_url)
    return True

def show_instructions():
    """Show step-by-step instructions"""
    print(f"\n{'='*70}")
    print("📋 SUPABASE SQL SETUP - STEP BY STEP")
    print(f"{'='*70}")
    
    print("\n✅ STEP 1: session_management_migration.sql")
    print("-" * 70)
    print("1. SQL Editor açıldı (tarayıcıda)")
    print("2. Aşağıdaki dosyayı aç:")
    print("   📁 database/session_management_migration.sql")
    print("3. TÜM içeriği kopyala (Ctrl+A → Ctrl+C)")
    print("4. Supabase SQL Editor'a yapıştır (Ctrl+V)")
    print("5. RUN butonuna tıkla ▶️")
    print("6. ✅ 'Success' mesajını gördüğünde buraya geri dön")
    
    input("\n⏸️  Press ENTER when STEP 1 is complete...")
    
    print("\n✅ STEP 2: supabase_rpc_functions.sql")
    print("-" * 70)
    print("1. SQL Editor'da NEW QUERY tıkla")
    print("2. Aşağıdaki dosyayı aç:")
    print("   📁 database/supabase_rpc_functions.sql")
    print("3. TÜM içeriği kopyala (Ctrl+A → Ctrl+C)")
    print("4. Supabase SQL Editor'a yapıştır (Ctrl+V)")
    print("5. RUN butonuna tıkla ▶️")
    print("6. ✅ 'Success' mesajını gördüğünde buraya geri dön")
    
    input("\n⏸️  Press ENTER when STEP 2 is complete...")
    
    return True

def main():
    print("\n🚀 PAZARGLOBAL - SUPABASE DATABASE SETUP")
    print("="*70)
    print("\n⚡ Otomatik setup başlıyor...")
    print(f"📍 Project: {PROJECT_ID}")
    print(f"🌐 URL: {SUPABASE_URL}\n")
    
    # Open SQL Editor
    open_sql_editor()
    
    # Show instructions
    show_instructions()
    
    print("\n" + "="*70)
    print("🎉 DATABASE SETUP COMPLETE!")
    print("="*70)
    
    print("\n📋 NEXT STEPS:")
    print("\n1️⃣  Deploy Edge Function:")
    print("    cd pazarglobal-agent-backend")
    print("    supabase functions deploy whatsapp-traffic-controller --project-ref snovwbffwvmkgjulrtsm")
    
    print("\n2️⃣  Add EDGE_FUNCTION_URL to Railway:")
    print("    EDGE_FUNCTION_URL=https://snovwbffwvmkgjulrtsm.supabase.co/functions/v1/whatsapp-traffic-controller")
    
    print("\n3️⃣  Test WhatsApp PIN:")
    print("    - WhatsApp'tan mesaj gönder")
    print("    - '🔒 PIN girin' mesajını gör")
    print("    - PIN gönder (örn: 1234)")
    print("    - '✅ Giriş başarılı' mesajını gör")
    
    print("\n" + "="*70)
    print("✨ Hazırsın! Edge Function deploy et ve test et.")
    print("="*70 + "\n")

if __name__ == "__main__":
    main()
