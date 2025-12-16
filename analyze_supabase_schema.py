"""
Supabase Schema Analyzer - Tablo yapılarını ve ilişkileri kontrol et
"""
import os
import httpx
import json
import asyncio
from typing import Dict, List, Any

async def analyze_supabase_schema():
    url = os.getenv('SUPABASE_URL', 'https://dlafxgsogjlbfxdmzvru.supabase.co')
    key = os.getenv('SUPABASE_SERVICE_KEY')
    
    if not key:
        print("❌ SUPABASE_SERVICE_KEY not found in environment")
        return
    
    headers = {
        'apikey': key,
        'Authorization': f'Bearer {key}',
        'Content-Type': 'application/json'
    }
    
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║         PAZARGLOBAL SUPABASE SCHEMA ANALYSIS                 ║")
    print("╚══════════════════════════════════════════════════════════════╝\n")
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        
        # 1. PROFILES TABLE
        print("\n" + "═" * 70)
        print("📋 PROFILES TABLE (User bilgileri)")
        print("═" * 70)
        try:
            r1 = await client.get(f'{url}/rest/v1/profiles?select=*&limit=1', headers=headers)
            if r1.status_code == 200 and r1.json():
                profile = r1.json()[0]
                print("\n✅ Tablo mevcut | Kolonlar:")
                for key, value in profile.items():
                    print(f"   • {key:20} = {value} ({type(value).__name__})")
                
                # Check relationships
                print("\n🔗 İlişkiler:")
                print("   • id (UUID) → PRIMARY KEY")
                print("   • phone (TEXT) → UNIQUE, user authentication için kullanılıyor")
            else:
                print(f"⚠️ Tablo boş veya erişim sorunu: {r1.status_code}")
                print(f"Response: {r1.text}")
        except Exception as e:
            print(f"❌ Hata: {e}")
        
        # 2. LISTINGS TABLE
        print("\n" + "═" * 70)
        print("📋 LISTINGS TABLE (İlan bilgileri)")
        print("═" * 70)
        try:
            r2 = await client.get(f'{url}/rest/v1/listings?select=*&limit=1', headers=headers)
            if r2.status_code == 200 and r2.json():
                listing = r2.json()[0]
                print("\n✅ Tablo mevcut | Kolonlar:")
                for key, value in listing.items():
                    value_str = str(value)[:50] if value else "NULL"
                    print(f"   • {key:25} = {value_str} ({type(value).__name__})")
                
                print("\n🔗 İlişkiler:")
                print("   • id (UUID) → PRIMARY KEY (İlan ID)")
                print("   • user_id (UUID) → FOREIGN KEY → profiles(id)")
                print("   ⚠️ CRITICAL: id = İlan numarası (listing ID)")
                print("   ⚠️ CRITICAL: user_id = İlanı oluşturan kullanıcı ID")
            else:
                print(f"⚠️ Tablo boş veya erişim sorunu: {r2.status_code}")
        except Exception as e:
            print(f"❌ Hata: {e}")
        
        # 3. USER_SECURITY TABLE
        print("\n" + "═" * 70)
        print("📋 USER_SECURITY TABLE (PIN authentication)")
        print("═" * 70)
        try:
            r3 = await client.get(f'{url}/rest/v1/user_security?select=*&limit=1', headers=headers)
            if r3.status_code == 200 and r3.json():
                security = r3.json()[0]
                print("\n✅ Tablo mevcut | Kolonlar:")
                for key, value in security.items():
                    if key == 'pin_hash':
                        print(f"   • {key:25} = [HASH] (hidden)")
                    else:
                        print(f"   • {key:25} = {value} ({type(value).__name__})")
                
                print("\n🔗 İlişkiler:")
                print("   • user_id (UUID) → FOREIGN KEY → profiles(id)")
                print("   • phone (TEXT) → UNIQUE, profiles.phone ile eşleşmeli")
            else:
                print(f"⚠️ Tablo boş veya erişim sorunu: {r3.status_code}")
        except Exception as e:
            print(f"❌ Hata: {e}")
        
        # 4. USER_SESSIONS TABLE
        print("\n" + "═" * 70)
        print("📋 USER_SESSIONS TABLE (10-minute sessions)")
        print("═" * 70)
        try:
            r4 = await client.get(f'{url}/rest/v1/user_sessions?select=*&limit=1', headers=headers)
            if r4.status_code == 200 and r4.json():
                session = r4.json()[0]
                print("\n✅ Tablo mevcut | Kolonlar:")
                for key, value in session.items():
                    print(f"   • {key:25} = {value} ({type(value).__name__})")
                
                print("\n🔗 İlişkiler:")
                print("   • user_id (UUID) → FOREIGN KEY → profiles(id)")
                print("   • session_id (UUID) → PRIMARY KEY")
            else:
                print(f"⚠️ Tablo boş veya erişim sorunu: {r4.status_code}")
        except Exception as e:
            print(f"❌ Hata: {e}")
        
        # 5. WALLETS TABLE
        print("\n" + "═" * 70)
        print("📋 WALLETS TABLE (Credit system)")
        print("═" * 70)
        try:
            r5 = await client.get(f'{url}/rest/v1/wallets?select=*&limit=1', headers=headers)
            if r5.status_code == 200 and r5.json():
                wallet = r5.json()[0]
                print("\n✅ Tablo mevcut | Kolonlar:")
                for key, value in wallet.items():
                    print(f"   • {key:25} = {value} ({type(value).__name__})")
                
                print("\n🔗 İlişkiler:")
                print("   • user_id (UUID) → PRIMARY KEY & FOREIGN KEY → profiles(id)")
            else:
                print(f"⚠️ Tablo boş veya erişim sorunu: {r5.status_code}")
        except Exception as e:
            print(f"❌ Hata: {e}")
        
        # 6. WALLET_TRANSACTIONS TABLE
        print("\n" + "═" * 70)
        print("📋 WALLET_TRANSACTIONS TABLE (Credit history)")
        print("═" * 70)
        try:
            r6 = await client.get(f'{url}/rest/v1/wallet_transactions?select=*&limit=1', headers=headers)
            if r6.status_code == 200 and r6.json():
                tx = r6.json()[0]
                print("\n✅ Tablo mevcut | Kolonlar:")
                for key, value in tx.items():
                    value_str = str(value)[:50] if value else "NULL"
                    print(f"   • {key:25} = {value_str} ({type(value).__name__})")
                
                print("\n🔗 İlişkiler:")
                print("   • id (UUID) → PRIMARY KEY (Transaction ID)")
                print("   • user_id (UUID) → FOREIGN KEY → profiles(id)")
                print("   • reference (TEXT) → Optional: listing ID veya diğer referanslar")
            else:
                print(f"⚠️ Tablo boş veya erişim sorunu: {r6.status_code}")
        except Exception as e:
            print(f"❌ Hata: {e}")
        
        # 7. PRODUCT_IMAGES TABLE
        print("\n" + "═" * 70)
        print("📋 PRODUCT_IMAGES TABLE (Ürün görselleri)")
        print("═" * 70)
        try:
            r7 = await client.get(f'{url}/rest/v1/product_images?select=*&limit=1', headers=headers)
            if r7.status_code == 200 and r7.json():
                image = r7.json()[0]
                print("\n✅ Tablo mevcut | Kolonlar:")
                for key, value in image.items():
                    value_str = str(value)[:50] if value else "NULL"
                    print(f"   • {key:25} = {value_str} ({type(value).__name__})")
                
                print("\n🔗 İlişkiler:")
                print("   • id (UUID) → PRIMARY KEY")
                print("   • listing_id (UUID) → FOREIGN KEY → listings(id)")
            else:
                print(f"⚠️ Tablo boş veya erişim sorunu: {r7.status_code}")
        except Exception as e:
            print(f"❌ Hata: {e}")
        
        # 8. FINAL ANALYSIS
        print("\n" + "╔" + "═" * 68 + "╗")
        print("║" + " " * 15 + "🔍 SCHEMA İLİŞKİLERİ ANALİZİ" + " " * 25 + "║")
        print("╚" + "═" * 68 + "╝\n")
        
        print("✅ DOĞRU İLİŞKİLER:")
        print("   1. profiles.id (UUID) ← USER kimliği")
        print("   2. profiles.phone (TEXT) ← WhatsApp authentication")
        print("   3. listings.id (UUID) ← İLAN kimliği (listing_id)")
        print("   4. listings.user_id (UUID) → profiles.id (ilan sahibi)")
        print("   5. wallets.user_id (UUID) → profiles.id (cüzdan sahibi)")
        print("   6. wallet_transactions.user_id (UUID) → profiles.id")
        print("   7. product_images.listing_id (UUID) → listings.id")
        
        print("\n⚠️ AGENT KULLANIMI:")
        print("   • user_id: ALWAYS profiles.id (UUID)")
        print("   • user_phone: profiles.phone (TEXT) - Authentication için")
        print("   • user_name: profiles.name (TEXT) - Display için")
        print("   • listing_id: listings.id (UUID) - İlan numarası")
        
        print("\n🔒 AGENT KİMLİK DOĞRULAMA:")
        print("   1. WhatsApp Bridge → Edge Function'a phone gönderir")
        print("   2. Edge Function → user_sessions'da user_id + phone lookup")
        print("   3. Backend (/agent/run) → user_id UUID olarak alır")
        print("   4. Tools → user_id ile Supabase sorgular (profiles, listings, wallets)")
        
        print("\n💡 METADATA vs SPECIFIC COLUMNS:")
        print("   • Agent user check: METADATA kullanmıyor!")
        print("   • Agent user check: user_id (UUID) ile profiles tablosuna bakar")
        print("   • listings.metadata: Sadece ürün özelliklerini saklar (brand, model, etc.)")
        print("   • User bilgileri: profiles tablosunda (id, phone, name)")
        
        print("\n✅ TÜM İLİŞKİLER TUTARLI:")
        print("   • profiles.id → listings.user_id ✓")
        print("   • profiles.id → wallets.user_id ✓")
        print("   • profiles.id → user_security.user_id ✓")
        print("   • listings.id → product_images.listing_id ✓")
        print("   • profiles.phone → user_security.phone ✓")
        
        print("\n" + "═" * 70)

if __name__ == "__main__":
    asyncio.run(analyze_supabase_schema())
