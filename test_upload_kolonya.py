"""
Direct test: Upload kolonya image to Supabase Storage + create listing
"""
import asyncio
import sys
import os
import httpx
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

async def main():
    from tools.insert_listing import insert_listing
    
    print("🧪 Test: Upload Kolonya Image to Storage")
    print("=" * 60)
    
    # Env check
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_KEY")
    supabase_bucket = os.getenv("SUPABASE_STORAGE_BUCKET", "product-images")
    
    if not supabase_url or not supabase_key:
        print("❌ Environment variables missing!")
        return
    
    print(f"✅ SUPABASE_URL: {supabase_url[:40]}...")
    print(f"✅ STORAGE_BUCKET: {supabase_bucket}")
    
    # Hardcoded image path
    image_path = r"C:\Users\emrah badas\Downloads\WhatsApp Image 2025-12-06 at 01.21.13.jpeg"
    local_file = Path(image_path)
    
    print(f"\n📸 Image: {local_file.name}")
    
    if not local_file.exists():
        print(f"❌ File not found: {image_path}")
        return
    
    print(f"✅ File exists ({local_file.stat().st_size} bytes)")
    
    # Generate listing ID and storage path
    listing_id = str(uuid.uuid4())
    storage_path = f"test-real/{listing_id}/{local_file.name}"
    
    print(f"\n📤 Uploading to Storage...")
    print(f"   Path: {storage_path}")
    
    # Read file
    with open(local_file, 'rb') as f:
        file_content = f.read()
    
    # Upload to Supabase Storage
    upload_url = f"{supabase_url}/storage/v1/object/{supabase_bucket}/{storage_path}"
    headers = {
        "Content-Type": "image/jpeg",
        "Authorization": f"Bearer {supabase_key}",
        "apikey": supabase_key,
    }
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(upload_url, content=file_content, headers=headers)
    
    if resp.status_code not in (200, 201):
        print(f"❌ Upload failed ({resp.status_code}): {resp.text}")
        return
    
    print(f"✅ Uploaded successfully!")
    print(f"   Storage path: {storage_path}")
    
    # Create listing with image
    print(f"\n🚀 Creating listing in DB...")
    
    result = await insert_listing(
        title="Test Kolonya - Gerçek Fotoğraflı",
        user_id="a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11",
        price=99,
        condition="new",
        category="Kozmetik & Bakım",
        description="Test: Gerçek fotoğraf yüklemeli kolonya ilanı",
        location="İstanbul",
        stock=3,
        metadata={"type": "general", "test": "real_upload"},
        images=[storage_path],
        listing_id=listing_id
    )
    
    print("\n" + "=" * 60)
    print("📊 RESULT:")
    print("=" * 60)
    print(f"Success: {result.get('success')}")
    print(f"Status: {result.get('status')}")
    
    if result.get('success'):
        data = result.get('result', [])
        if isinstance(data, list) and data:
            data = data[0]
        
        print(f"\n✅ Listing Created!")
        print(f"   ID: {data.get('id')}")
        print(f"   Title: {data.get('title')}")
        print(f"   Category: {data.get('category')}")
        print(f"   Images: {data.get('images')}")
        print(f"   Image URL: {data.get('image_url')}")
        
        print(f"\n📷 Check Supabase Storage:")
        print(f"   Bucket: {supabase_bucket}")
        print(f"   Path: {storage_path}")
        print(f"\n🔗 Direct link: {supabase_url}/storage/v1/object/public/{supabase_bucket}/{storage_path}")
    else:
        print(f"\n❌ Failed: {result.get('error')}")
    
    print("\n" + "=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
