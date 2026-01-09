"""
SearchComposerAgent manuel test script
"""
import asyncio
import sys
import os
from dotenv import load_dotenv

# Load environment variables first
load_dotenv()

# Add parent directory to path
sys.path.insert(0, os.path.dirname(__file__))

from services.listing_search import SearchComposerAgent


async def test_search():
    """Test SearchComposerAgent with various queries"""
    
    composer = SearchComposerAgent(preview_limit=5, fetch_limit=30)
    
    test_queries = [
        "citroen",
        "araba",
        "otomotiv",
        "380000 tl araba",
    ]
    
    print("=" * 80)
    print("SearchComposerAgent Manuel Test")
    print("=" * 80)
    
    for query in test_queries:
        print(f"\nTEST QUERY: '{query}'")
        print("-" * 80)
        
        try:
            result = await composer.orchestrate_search(
                user_message=query
            )
            
            print("SUCCESS")
            print(f"Message Length: {len(result.get('message', ''))}")
            print(f"Listings Count: {len(result.get('listings', []))}")
            print(f"Total: {result.get('total', 0)}")
            print(f"\nMessage:\n{result.get('message', 'N/A')[:500]}")
            
        except Exception as e:
            print(f"ERROR: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "=" * 80)
    print("Test Completed")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(test_search())
