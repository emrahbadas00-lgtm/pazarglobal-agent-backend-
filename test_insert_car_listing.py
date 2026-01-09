"""
Test: Insert car listing to Supabase
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from tools.insert_listing import insert_listing


async def test_insert():
    """Insert a test car listing"""
    
    test_data = {
        "user_id": "3ec55e9d-93e8-40c5-8e0e-7dc933da997f",  # Emrah's user_id
        "title": "Satılık 2018 Model Volkswagen Golf",
        "category": "Otomotiv",
        "price": 450000,
        "description": "2018 model Volkswagen Golf 1.6 TDI Highline. 85.000 km'de, hasarsız, ilk elden. Full+Full donanım, otomatik vites, deri koltuk.",
        "condition": "İkinci El",
        "images": [],
    }
    
    print("=" * 80)
    print("Test: Insert Car Listing")
    print("=" * 80)
    print(f"📝 Title: {test_data['title']}")
    print(f"💰 Price: {test_data['price']} TL")
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
