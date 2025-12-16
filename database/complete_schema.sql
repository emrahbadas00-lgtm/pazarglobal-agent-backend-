-- ============================================================
-- PAZARGLOBAL - COMPLETE DATABASE SCHEMA
-- Generated: 2025-11-29
-- ============================================================
-- Bu dosya tüm Supabase tablolarını, RLS politikalarını, 
-- storage bucket yapılandırmalarını içerir
-- ============================================================

-- ============================================================
-- TABLE: users
-- User bilgileri (WhatsApp entegrasyonu için)
-- ============================================================
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    phone TEXT UNIQUE NOT NULL,  -- WhatsApp phone number
    name TEXT,
    email TEXT,
    location TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_users_phone ON users(phone);
CREATE INDEX idx_users_created_at ON users(created_at DESC);

-- RLS Policies (placeholder - auth.uid() ile güncellenecek)
ALTER TABLE users ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own profile"
    ON users FOR SELECT
    USING (true);  -- TODO: auth.uid() = id

CREATE POLICY "Users can update own profile"
    ON users FOR UPDATE
    USING (true)  -- TODO: auth.uid() = id
    WITH CHECK (true);

-- Auto-update updated_at
CREATE TRIGGER update_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();


-- ============================================================
-- TABLE: listings
-- İlan bilgileri
-- ============================================================
CREATE TABLE IF NOT EXISTS listings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    description TEXT,
    category TEXT,
    price NUMERIC(10, 2) NOT NULL CHECK (price >= 0),
    stock INTEGER DEFAULT 1 CHECK (stock >= 0),
    location TEXT,
    status TEXT DEFAULT 'draft' CHECK (status IN ('draft', 'active', 'sold', 'inactive')),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    view_count INTEGER DEFAULT 0,
    market_price_at_publish NUMERIC(10, 2),
    last_price_check_at TIMESTAMPTZ,
    condition TEXT CHECK (condition IN ('new', 'used', 'refurbished')),
    image_url TEXT,
    metadata JSONB DEFAULT '{}'::jsonb
);

-- Indexes
CREATE INDEX idx_listings_user_id ON listings(user_id);
CREATE INDEX idx_listings_status ON listings(status);
CREATE INDEX idx_listings_category ON listings(category);
CREATE INDEX idx_listings_created_at ON listings(created_at DESC);
CREATE INDEX idx_listings_price ON listings(price);

-- Full-text search indexes
CREATE INDEX idx_listings_title_search ON listings USING gin(to_tsvector('turkish', title));
CREATE INDEX idx_listings_description_search ON listings USING gin(to_tsvector('turkish', description));

-- RLS Policies
ALTER TABLE listings ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Anyone can view active listings"
    ON listings FOR SELECT
    USING (status = 'active' OR true);  -- TODO: OR user_id = auth.uid()

CREATE POLICY "Users can insert own listings"
    ON listings FOR INSERT
    WITH CHECK (true);  -- TODO: user_id = auth.uid()

CREATE POLICY "Users can update own listings"
    ON listings FOR UPDATE
    USING (true)  -- TODO: user_id = auth.uid()
    WITH CHECK (true);

CREATE POLICY "Users can delete own listings"
    ON listings FOR DELETE
    USING (true);  -- TODO: user_id = auth.uid()

-- Auto-update updated_at
CREATE TRIGGER update_listings_updated_at
    BEFORE UPDATE ON listings
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();


-- ============================================================
-- TABLE: conversations
-- WhatsApp konuşma geçmişi
-- ============================================================
CREATE TABLE IF NOT EXISTS conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    whatsapp_chat_id TEXT NOT NULL,  -- WhatsApp conversation ID
    last_message_at TIMESTAMPTZ DEFAULT NOW(),
    message_count INTEGER DEFAULT 0,
    status TEXT DEFAULT 'active' CHECK (status IN ('active', 'archived')),
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_conversations_user_id ON conversations(user_id);
CREATE INDEX idx_conversations_whatsapp_chat_id ON conversations(whatsapp_chat_id);
CREATE INDEX idx_conversations_last_message_at ON conversations(last_message_at DESC);

-- RLS Policies
ALTER TABLE conversations ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own conversations"
    ON conversations FOR SELECT
    USING (true);  -- TODO: user_id = auth.uid()

CREATE POLICY "System can insert conversations"
    ON conversations FOR INSERT
    WITH CHECK (true);  -- Service role only

-- Auto-update updated_at
CREATE TRIGGER update_conversations_updated_at
    BEFORE UPDATE ON conversations
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();


-- ============================================================
-- TABLE: orders
-- Sipariş/satış işlemleri
-- ============================================================
CREATE TABLE IF NOT EXISTS orders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    listing_id UUID NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
    buyer_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    seller_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    price NUMERIC(10, 2) NOT NULL CHECK (price >= 0),
    commission NUMERIC(10, 2) DEFAULT 0 CHECK (commission >= 0),
    seller_receives NUMERIC(10, 2) NOT NULL CHECK (seller_receives >= 0),
    quantity INTEGER DEFAULT 1 CHECK (quantity > 0),
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'completed', 'cancelled')),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

-- Indexes
CREATE INDEX idx_orders_listing_id ON orders(listing_id);
CREATE INDEX idx_orders_buyer_id ON orders(buyer_id);
CREATE INDEX idx_orders_seller_id ON orders(seller_id);
CREATE INDEX idx_orders_status ON orders(status);
CREATE INDEX idx_orders_created_at ON orders(created_at DESC);

-- RLS Policies
ALTER TABLE orders ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own orders"
    ON orders FOR SELECT
    USING (true);  -- TODO: buyer_id = auth.uid() OR seller_id = auth.uid()

CREATE POLICY "System can create orders"
    ON orders FOR INSERT
    WITH CHECK (true);  -- Service role only

CREATE POLICY "Users can update own orders"
    ON orders FOR UPDATE
    USING (true);  -- TODO: buyer_id = auth.uid() OR seller_id = auth.uid()


-- ============================================================
-- TABLE: product_embeddings
-- Semantic search için OpenAI embeddings
-- ============================================================
CREATE TABLE IF NOT EXISTS product_embeddings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    listing_id UUID NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
    embedding vector(1536),  -- OpenAI text-embedding-3-small dimension
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(listing_id)
);

-- Indexes
CREATE INDEX idx_product_embeddings_listing_id ON product_embeddings(listing_id);

-- Vector similarity search index (requires pgvector extension)
-- CREATE INDEX ON product_embeddings USING ivfflat (embedding vector_cosine_ops);

-- RLS Policies
ALTER TABLE product_embeddings ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Anyone can view embeddings"
    ON product_embeddings FOR SELECT
    USING (true);

CREATE POLICY "System can manage embeddings"
    ON product_embeddings FOR ALL
    USING (true)  -- Service role only
    WITH CHECK (true);


-- ============================================================
-- TABLE: product_images
-- Ürün görselleri (Storage bucket referansları)
-- ============================================================
CREATE TABLE IF NOT EXISTS product_images (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    listing_id UUID NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
    storage_path TEXT NOT NULL,  -- Path in 'product-images' bucket
    display_order INTEGER DEFAULT 0,
    is_primary BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_product_images_listing_id ON product_images(listing_id);
CREATE INDEX idx_product_images_display_order ON product_images(display_order);

-- RLS Policies
ALTER TABLE product_images ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Anyone can view product images"
    ON product_images FOR SELECT
    USING (true);

CREATE POLICY "Users can manage own product images"
    ON product_images FOR ALL
    USING (
        EXISTS (
            SELECT 1 FROM listings
            WHERE listings.id = product_images.listing_id
            -- AND listings.user_id = auth.uid()  -- TODO: Enable with auth
        )
    );


-- ============================================================
-- TABLE: notifications
-- Kullanıcı bildirimleri (WhatsApp mesajları için)
-- ============================================================
CREATE TABLE IF NOT EXISTS notifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    type TEXT NOT NULL CHECK (type IN ('order', 'message', 'listing', 'system')),
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    read BOOLEAN DEFAULT false,
    data JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_notifications_user_id ON notifications(user_id);
CREATE INDEX idx_notifications_read ON notifications(read);
CREATE INDEX idx_notifications_created_at ON notifications(created_at DESC);
CREATE INDEX idx_notifications_type ON notifications(type);

-- RLS Policies
ALTER TABLE notifications ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own notifications"
    ON notifications FOR SELECT
    USING (true);  -- TODO: user_id = auth.uid()

CREATE POLICY "System can create notifications"
    ON notifications FOR INSERT
    WITH CHECK (true);  -- Service role only

CREATE POLICY "Users can update own notifications"
    ON notifications FOR UPDATE
    USING (true);  -- TODO: user_id = auth.uid()


-- ============================================================
-- HELPER FUNCTIONS
-- ============================================================

-- Function to auto-update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;


-- ============================================================
-- STORAGE BUCKETS
-- ============================================================

-- Bucket: product-images
-- Purpose: Ürün görselleri (public access)
-- Settings:
--   - Public: Yes
--   - File size limit: 5 MB
--   - Allowed MIME types: image/jpeg, image/png, image/webp, image/jpg
--   - Policies: 2

-- Bucket: user-documents
-- Purpose: Kullanıcı belgeleri (private)
-- Settings:
--   - Public: No
--   - File size limit: 10 MB
--   - Allowed MIME types: application/pdf, image/jpeg, image/png
--   - Policies: 4


-- ============================================================
-- STORAGE POLICIES
-- ============================================================

-- product-images bucket policies
-- Policy 1: Anyone can view public images
-- Policy 2: Users can upload/delete own images

-- user-documents bucket policies
-- Policy 1: Users can view own documents
-- Policy 2: Users can upload own documents
-- Policy 3: Users can update own documents
-- Policy 4: Users can delete own documents


-- ============================================================
-- EXTENSIONS REQUIRED
-- ============================================================
-- CREATE EXTENSION IF NOT EXISTS "uuid-ossp";     -- UUID generation
-- CREATE EXTENSION IF NOT EXISTS "vector";         -- pgvector for embeddings
-- CREATE EXTENSION IF NOT EXISTS "pg_trgm";        -- Trigram similarity for fuzzy search


-- ============================================================
-- NOTES & TODO
-- ============================================================
-- 1. RLS policies currently use 'true' for development
--    → Replace with auth.uid() when Supabase Auth is integrated
-- 
-- 2. WhatsApp integration phase will require:
--    - user_id parameter in all tools
--    - Conversation tracking
--    - Message history
--
-- 3. Storage bucket policies need to be configured in Supabase UI:
--    - product-images: Public read, authenticated write
--    - user-documents: Authenticated users only
--
-- 4. Vector search requires pgvector extension:
--    - Enable in Supabase dashboard
--    - Create IVFFlat index for similarity search
--
-- 5. Missing tables for future development:
--    - messages: WhatsApp message history
--    - sessions: Agent conversation context
--    - analytics: User behavior tracking
--    - reviews: Product/seller ratings
