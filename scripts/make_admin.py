"""
Make user admin and add initial test credits
"""
from supabase import create_client

# Hardcoded for quick test (remove after use)
SUPABASE_URL = "https://snovwbffwvmkgjulrtsm.supabase.co"
SUPABASE_SERVICE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InNub3Z3YmZmd3Zta2dqdWxydHNtIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc2MzIzNTc0NCwiZXhwIjoyMDc4ODExNzQ0fQ.JlgKvo9PYDOix7HYjPUo59RvrCdjruf5PxCdxgPklCs"

supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

def make_admin(phone_or_email: str):
    """Make user admin by phone or email"""
    # Find user
    if phone_or_email.startswith("+"):
        # Phone lookup
        result = supabase.table("profiles").select("*").eq("phone", phone_or_email).execute()
    else:
        # Email lookup
        result = supabase.table("profiles").select("*").eq("email", phone_or_email).execute()
    
    if not result.data or len(result.data) == 0:
        print(f"❌ User not found: {phone_or_email}")
        return
    
    user = result.data[0]
    if not isinstance(user, dict):
        print(f"❌ Invalid user data")
        return
        
    user_id = user.get("id")
    if not user_id:
        print(f"❌ User ID not found")
        return
    
    print(f"✅ Found user: {user.get('display_name', 'Unknown')} ({user_id})")
    
    # Make admin
    supabase.table("profiles").update({
        "role": "admin"
    }).eq("id", user_id).execute()
    
    print(f"✅ User is now ADMIN")
    
    # Add 1000 test credits (₺200 worth)
    credit_amount = 1000 * 100  # 1000 credits = 100000 bigint units
    
    supabase.rpc("credit_wallet", {
        "p_user": user_id,
        "p_amount_bigint": credit_amount,
        "p_kind": "admin_adjust",
        "p_reference": "initial_test_credits",
        "p_metadata": {"reason": "Test environment setup"}
    }).execute()
    
    print(f"✅ Added 1000 test credits (₺200)")
    print(f"\n🎉 Setup complete!")
    print(f"   User ID: {user_id}")
    print(f"   Role: admin")
    print(f"   Balance: 1000 credits (₺200)")

if __name__ == "__main__":
    # Emrah's credentials
    phone_or_email = "emrahbadas@gmail.com"
    
    print(f"🔍 Looking up user: {phone_or_email}")
    make_admin(phone_or_email)
