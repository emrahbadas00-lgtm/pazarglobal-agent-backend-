"""
Simple test: Insert kolonya listing to Supabase
Run from pazarglobal-agent-backend directory
"""
import asyncio
import sys
from pathlib import Path

# Ensure we can import tools
sys.path.insert(0, str(Path(__file__).parent))

async def main():
    # Import after path is set
    from tools.insert_listing import insert_listing
    import os
    import httpx
    import uuid
    
    print("🧪 Test: Insert Listing with Images + Storage Upload")
    print("=" * 60)
    
    # Check env
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_KEY")
    supabase_bucket = os.getenv("SUPABASE_STORAGE_BUCKET", "product-images")
    
    print(f"\n🔧 Environment Check:")
    print(f"   SUPABASE_URL: {supabase_url[:40] if supabase_url else '❌ NOT SET'}...")
    print(f"   SUPABASE_KEY: {supabase_key[:20] if supabase_key else '❌ NOT SET'}...")
    print(f"   STORAGE_BUCKET: {supabase_bucket}")
    
    if not supabase_url or not supabase_key:
        print("\n❌ ERROR: Environment variables not set!")
        print("Make sure to run from backend dir with .env loaded")
        return
    
    # Get image paths from user
    print("\n" + "=" * 60)
    print("📸 Enter image path (or 'skip' for no images):")
    print("Example: C:\\Users\\emrah badas\\Downloads\\kolonya.jpg")
    print("\nPath: ", end="")
    
    user_input = input().strip().strip('"').strip("'")
    
    images = None
    if user_input.lower() != 'skip':
        local_path = Path(user_input)
        if local_path.exists():
            print(f"✅ File found: {local_path.name}")
            
            # Upload to Supabase Storage
            print("📤 Uploading to Supabase Storage...")
            
            listing_id = str(uuid.uuid4())
            storage_path = f"test-manual/{listing_id}/{local_path.name}"
            
            # Read file
            with open(local_path, 'rb') as f:
                file_content = f.read()
            
            # Determine content type
            ext = local_path.suffix.lower()
            content_type = {
                '.jpg': 'image/jpeg',
                '.jpeg': 'image/jpeg',
                '.png': 'image/png',
                '.gif': 'image/gif',
                '.webp': 'image/webp'
            }.get(ext, 'image/jpeg')
            
            # Upload
            upload_url = f"{supabase_url}/storage/v1/object/{supabase_bucket}/{storage_path}"
            headers = {
                "Content-Type": content_type,
                "Authorization": f"Bearer {supabase_key}",
                "apikey": supabase_key,
            }
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(upload_url, content=file_content, headers=headers)
            
            if resp.status_code in (200, 201):
                print(f"✅ Uploaded to Storage: {storage_path}")
                images = [storage_path]
            else:
                print(f"❌ Upload failed ({resp.status_code}): {resp.text}")
                print("⚠️  Continuing without images...")
        else:
            print(f"❌ File not found: {user_input}")
            print("⚠️  Continuing without images...")
    
    # Prepare test data
    test_data = {
        "title": "Test Limon Kolonyası - 100ml",
        "user_id": "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11",
        "price": 75,
        "condition": "new",
        "category": "Kozmetik & Bakım",
        "description": "Test: 100ml limon kolonyası, el yapımı",
        "location": "İstanbul",
        "stock": 5,
        "metadata": {"type": "general", "scent": "limon"},
        "images": images
    }
    
    print("\n" + "=" * 60)
    print("🚀 Inserting listing...")
    print("=" * 60)
    
    result = await insert_listing(**test_data)
    
    print("\n📊 RESULT:")
    print(f"   Success: {result.get('success')}")
    print(f"   Status: {result.get('status')}")
    
    if result.get('success'):
        data = result.get('result', [])
        if isinstance(data, list) and data:
            data = data[0]
        print(f"\n✅ Listing Created!")
        print(f"   ID: {data.get('id')}")
        print(f"   Title: {data.get('title')}")
        print(f"   Category: {data.get('category')}")
        print(f"   Images: {data.get('images')}")
    else:
        print(f"\n❌ Failed: {result.get('error')}")
    
    print("\n" + "=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
