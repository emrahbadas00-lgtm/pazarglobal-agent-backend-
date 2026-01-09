"""Test search functionality and check listings"""
import os
import sys
import asyncio
from dotenv import load_dotenv

load_dotenv()

# Test 1: Check if listings exist
async def check_listings():
    import httpx
    url = os.getenv('SUPABASE_URL') + '/rest/v1/listings'
    headers = {
        'apikey': os.getenv('SUPABASE_ANON_KEY'),
        'Authorization': f'Bearer {os.getenv("SUPABASE_ANON_KEY")}'
    }
    
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url + '?select=id,title,category&limit=10', headers=headers)
        print(f"✅ Supabase status: {resp.status_code}")
        data = resp.json()
        print(f"📦 İlan sayısı: {len(data)}")
        for i, item in enumerate(data):
            print(f"  {i+1}. {item.get('title')} ({item.get('category')})")
        return data

# Test 2: Test search composer
async def test_search_composer():
    from services.listing_search import SearchComposerAgent
    
    print("\n🔍 Testing SearchComposerAgent...")
    composer = SearchComposerAgent(preview_limit=5, fetch_limit=30)
    
    result = await composer.orchestrate_search(
        user_key="test_user",
        query_text="araba"
    )
    
    print(f"\n✅ Composer result keys: {list(result.keys())}")
    print(f"📝 Message length: {len(result.get('message', ''))}")
    print(f"💾 Cache count: {len(result.get('cache', []))}")
    print(f"\n📄 Message preview:\n{result.get('message', '')[:500]}")

# Test 3: Test workflow
async def test_workflow():
    from workflow import _handle_search_intent
    
    print("\n🎯 Testing workflow search handler...")
    result = await _handle_search_intent("test_user", "araba varmı")
    
    print(f"\n✅ Workflow result keys: {list(result.keys())}")
    print(f"📝 Message: {result.get('message', '')[:200]}")

async def main():
    print("=" * 60)
    print("🧪 SEARCH DEBUG TEST")
    print("=" * 60)
    
    try:
        # Test 1
        print("\n1️⃣ Checking Supabase listings...")
        listings = await check_listings()
        
        if not listings:
            print("\n❌ VERİTABANINDA İLAN YOK!")
            print("   Önce ilan eklemen gerekiyor.")
            return
        
        # Test 2
        print("\n2️⃣ Testing SearchComposerAgent...")
        await test_search_composer()
        
        # Test 3
        print("\n3️⃣ Testing workflow integration...")
        await test_workflow()
        
        print("\n" + "=" * 60)
        print("✅ TÜM TESTLER TAMAMLANDI")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ HATA: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
