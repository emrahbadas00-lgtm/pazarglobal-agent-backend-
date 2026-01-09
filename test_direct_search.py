"""
Test search_listings tool directly
"""
import asyncio
import sys
import os
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.dirname(__file__))

from tools.search_listings import search_listings


async def test_direct_search():
    """Test search_listings with various parameters"""
    
    tests = [
        {"query": "citroen", "category": None},
        {"query": None, "category": "Otomotiv"},
        {"query": None, "category": None, "search_text": "citroen"},
        {"query": "araba", "category": None},
    ]
    
    print("=" * 80)
    print("Direct Search Tool Test")
    print("=" * 80)
    
    for i, params in enumerate(tests, 1):
        print(f"\n🔍 TEST {i}: {params}")
        print("-" * 80)
        
        try:
            result = await search_listings(**params)
            
            listings = result.get("results", [])
            print(f"✅ Found {len(listings)} listings (total: {result.get('total', 0)})")
            
            if listings:
                for listing in listings[:3]:
                    print(f"  - {listing.get('title')} (ID: {listing.get('id')})")
            else:
                print(f"  ℹ️ Query returned 0 results but total={result.get('total', 0)}")
                
        except Exception as e:
            print(f"❌ ERROR: {type(e).__name__}: {e}")
    
    print("\n" + "=" * 80)


if __name__ == "__main__":
    asyncio.run(test_direct_search())
