"""
Test: Insert car listing with env loading
"""
import asyncio
import sys
import os
from dotenv import load_dotenv

# Load .env first
load_dotenv()

sys.path.insert(0, os.path.dirname(__file__))

from tools.insert_listing import insert_listing


async def test_insert():
    """Insert a test car listing"""
    
    # Check env variables
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_KEY")
    
    print("=" * 80)
    print("Environment Check")
    print("=" * 80)
    print(f"SUPABASE_URL: {'✅ Set' if supabase_url else '❌ Not Set'}")
    print(f"SUPABASE_SERVICE_KEY: {'✅ Set' if supabase_key else '❌ Not Set'}")
    print("=" * 80)
    
    if not supabase_url or not supabase_key:
        print("❌ Environment variables missing! Cannot proceed.")
        return
    
    test_data = {
        "user_id": "3ec55e9d-93e8-40c5-8e0e-7dc933da997f",
        "title": "2020 Model Citroen C3 Otomobil",
        "category": "Otomotiv",
        "price": 380000.0,
        "description": "2020 model Citroen C3 1.2 PureTech otomobil. 45.000 km'de, hasarsız, ilk sahibinden. Otomatik vites, dokunmatik ekran, geri görüş kamerası.",
        "condition": "used",
        "images": [],
    }
    
    print("\nTest: Insert Car Listing")
    print("=" * 80)
    print(f"📝 Title: {test_data['title']}")
    print(f"💰 Price: {test_data['price']:.0f} TL")
    print(f"📂 Category: {test_data['category']}")
    print("-" * 80)
    
    try:
        result = await insert_listing(**test_data)
        
        if result.get("success"):
            print(f"✅ SUCCESS!")
            print(f"🆔 Listing ID: {result.get('listing_id')}")
            print(f"📝 Message: {result.get('message')}")
        else:
            print(f"❌ FAILED!")
            print(f"📝 Message: {result.get('message')}")
            print(f"🐛 Error: {result.get('error')}")
            
    except Exception as e:
        print(f"❌ EXCEPTION: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
    
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(test_insert())
