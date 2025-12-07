"""
Test: Upload 3 photos and create listing with all 3
"""
import asyncio
import sys
import os
import httpx
import uuid
from pathlib import Path
from dotenv import load_dotenv

# Load env
load_dotenv()

sys.path.insert(0, str(Path(__file__).parent))

async def main():
    from tools.insert_listing import insert_listing
    
    print("🧪 Test: Upload 3 Photos to Single Listing")
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
    
    # Photo paths
    photo_paths = [
        r"C:\Users\emrah badas\Downloads\1.jpeg",
        r"C:\Users\emrah badas\Downloads\2.jpeg",
        r"C:\Users\emrah badas\Downloads\3.jpeg",
    ]
    
    # Generate single listing ID for all photos
    listing_id = str(uuid.uuid4())
    storage_paths = []
    
    print(f"\n📋 Listing ID: {listing_id}")
    print(f"📤 Uploading 3 photos...")
    
    for idx, photo_path in enumerate(photo_paths, 1):
        local_file = Path(photo_path)
        
        if not local_file.exists():
            print(f"❌ File not found: {photo_path}")
            continue
        
        print(f"\n📸 {idx}/3: {local_file.name} ({local_file.stat().st_size} bytes)")
        
        # Generate storage path
        storage_path = f"test-multi/{listing_id}/{idx}-{local_file.name}"
        
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
        
        if resp.status_code in (200, 201):
            print(f"   ✅ Uploaded: {storage_path}")
            storage_paths.append(storage_path)
        else:
            print(f"   ❌ Upload failed ({resp.status_code}): {resp.text}")
    
    if len(storage_paths) != 3:
        print(f"\n❌ Only {len(storage_paths)}/3 photos uploaded!")
        return
    
    print(f"\n✅ All 3 photos uploaded!")
    print(f"   Paths: {storage_paths}")
    
    # Create listing with 3 photos
    print(f"\n🚀 Creating listing in DB...")
    
    result = await insert_listing(
        title="Test Araba - 3 Fotoğraflı",
        user_id="a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11",
        price=995000,
        condition="used",
        category="Otomotiv",
        description="Test: 3 fotoğraflı araba ilanı - Citroen C3 2020",
        location="İstanbul",
        stock=1,
        metadata={"type": "vehicle", "brand": "Citroen", "model": "C3", "year": 2020},
        images=storage_paths,
        listing_id=listing_id
    )
    
    print("\n" + "=" * 60)
    print("📊 RESULT:")
    print("=" * 60)
    print(f"Success: {result.get('success')}")
    
    if result.get('success'):
        data = result.get('result', [])
        if isinstance(data, list) and data:
            data = data[0]
        
        print(f"\n✅ Listing Created!")
        print(f"   ID: {data.get('id')}")
        print(f"   Title: {data.get('title')}")
        print(f"   Images: {data.get('images')}")
        print(f"   Image count: {len(data.get('images', []))}")
        
        print(f"\n📱 WhatsApp'tan şunu yaz:")
        print(f"   'araba ilanlarını göster'")
        print(f"\n🎯 Bu ilanda 3 fotoğraf görünmeli!")
    else:
        print(f"\n❌ Failed: {result.get('error')}")
    
    print("\n" + "=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
