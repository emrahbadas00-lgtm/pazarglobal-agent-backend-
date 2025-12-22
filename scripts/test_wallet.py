"""
Test wallet and premium badge system
"""
import sys
import os
import pytest

# Set environment variables before importing tools
os.environ["SUPABASE_URL"] = "https://snovwbffwvmkgjulrtsm.supabase.co"
os.environ["SUPABASE_SERVICE_ROLE_KEY"] = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InNub3Z3YmZmd3Zta2dqdWxydHNtIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc2MzIzNTc0NCwiZXhwIjoyMDc4ODExNzQ0fQ.JlgKvo9PYDOix7HYjPUo59RvrCdjruf5PxCdxgPklCs"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.wallet_tools import (
    get_wallet_balance,
    calculate_listing_cost,
    deduct_credits,
    add_premium_to_listing,
    renew_listing
)
from tools.admin_tools import admin_add_credits, admin_grant_premium

@pytest.fixture
def user_id() -> str:
    """Return known UUID used in staging wallet tests."""
    return "3ec55e9d-93e8-40c5-8e0e-7dc933da997f"


def test_wallet_system(user_id: str):
    """Test entire wallet system"""
    
    print("=" * 60)
    print("🧪 WALLET SYSTEM TEST")
    print("=" * 60)
    
    # 1. Check balance
    print("\n1️⃣ Checking wallet balance...")
    balance = get_wallet_balance(user_id)
    print(f"   Balance: {balance.get('balance_credits')} credits (₺{balance.get('balance_try')})")
    
    # 2. Calculate listing cost
    print("\n2️⃣ Calculating listing cost...")
    cost = calculate_listing_cost(
        use_ai_assistant=True,
        photo_count=3,
        use_ai_photos=True,
        use_price_suggestion=True,
        use_description_expansion=True
    )
    print(f"   Base: {cost['breakdown']['base']}kr")
    print(f"   AI Assistant: {cost['breakdown']['ai_assistant']}kr")
    print(f"   Photos (3x): {cost['breakdown']['photo_analysis']}kr")
    print(f"   Price Suggestion: {cost['breakdown']['price_suggestion']}kr")
    print(f"   Description: {cost['breakdown']['description_expansion']}kr")
    print(f"   TOTAL: {cost['total_credits']}kr (₺{cost['total_try']})")
    
    # 3. Simulate listing publish (deduct credits)
    print("\n3️⃣ Simulating listing publish (25kr deduction)...")
    fake_listing_id = "test-listing-123"
    deduct = deduct_credits(
        user_id=user_id,
        amount_credits=25,
        action="listing_publish",
        reference=fake_listing_id
    )
    if deduct["success"]:
        print(f"   ✅ Deducted 25kr")
        print(f"   New balance: {deduct['new_balance_credits']}kr")
    else:
        print(f"   ❌ Error: {deduct.get('error')}")
    
    # 4. Check premium badge costs
    print("\n4️⃣ Premium Badge Options:")
    print(f"   🥇 Gold: 50kr (₺10) - 7 days")
    print(f"   💎 Platinum: 90kr (₺18) - 14 days")
    print(f"   💠 Diamond: 150kr (₺30) - 30 days")
    
    # 5. Check balance again
    print("\n5️⃣ Final balance check...")
    final_balance = get_wallet_balance(user_id)
    print(f"   Balance: {final_balance.get('balance_credits')}kr (₺{final_balance.get('balance_try')})")
    
    print("\n" + "=" * 60)
    print("✅ TEST COMPLETE")
    print("=" * 60)

if __name__ == "__main__":
    # Emrah's user ID
    user_id = "3ec55e9d-93e8-40c5-8e0e-7dc933da997f"
    
    print(f"Testing wallet for user: {user_id}\n")
    test_wallet_system(user_id)
