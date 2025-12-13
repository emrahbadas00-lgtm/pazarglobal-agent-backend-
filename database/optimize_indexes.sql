-- ================================================
-- PazarGlobal Database Optimization
-- Critical indexes for production performance
-- ================================================

-- Run this script in Supabase SQL Editor before launch!

-- ================================================
-- 1. LISTINGS TABLE INDEXES
-- ================================================

-- User listings lookup (çok sık kullanılıyor)
CREATE INDEX IF NOT EXISTS idx_listings_user_id 
ON listings(user_id);

-- Category filtering
CREATE INDEX IF NOT EXISTS idx_listings_category 
ON listings(category);

-- Location filtering
CREATE INDEX IF NOT EXISTS idx_listings_location 
ON listings(location);

-- Status filtering (active/sold/deleted)
CREATE INDEX IF NOT EXISTS idx_listings_status 
ON listings(status);

-- Recent listings (homepage, feeds)
CREATE INDEX IF NOT EXISTS idx_listings_created_at 
ON listings(created_at DESC);

-- Updated listings (for "recently updated" queries)
CREATE INDEX IF NOT EXISTS idx_listings_updated_at 
ON listings(updated_at DESC);

-- Price range filtering
CREATE INDEX IF NOT EXISTS idx_listings_price 
ON listings(price);

-- Condition filtering (new/used/refurbished)
CREATE INDEX IF NOT EXISTS idx_listings_condition 
ON listings(condition);

-- Composite index for common search queries
-- (status + category + location)
CREATE INDEX IF NOT EXISTS idx_listings_search_composite 
ON listings(status, category, location) 
WHERE status = 'active';

-- Full-text search on title (Turkish language support)
CREATE INDEX IF NOT EXISTS idx_listings_title_fts 
ON listings USING GIN(to_tsvector('turkish', title));

-- Full-text search on description (Turkish language support)
CREATE INDEX IF NOT EXISTS idx_listings_description_fts 
ON listings USING GIN(to_tsvector('turkish', description));

-- ================================================
-- 2. PROFILES TABLE INDEXES
-- ================================================

-- Phone number lookup (WhatsApp authentication)
CREATE INDEX IF NOT EXISTS idx_profiles_phone 
ON profiles(phone) 
WHERE phone IS NOT NULL;

-- Email lookup (web authentication)
CREATE INDEX IF NOT EXISTS idx_profiles_email 
ON profiles(email) 
WHERE email IS NOT NULL;

-- ================================================
-- 3. USER_SECURITY TABLE INDEXES
-- (If WhatsApp PIN system is enabled)
-- ================================================

CREATE INDEX IF NOT EXISTS idx_user_security_phone 
ON user_security(phone) 
WHERE phone IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_user_security_session 
ON user_security(session_token) 
WHERE session_token IS NOT NULL;

-- ================================================
-- 4. ANALYZE TABLES
-- Update statistics for query planner
-- ================================================

ANALYZE listings;
ANALYZE profiles;
ANALYZE user_security;

-- ================================================
-- 5. VERIFICATION QUERIES
-- Check if indexes were created successfully
-- ================================================

-- List all indexes on listings table
SELECT 
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE tablename = 'listings'
ORDER BY indexname;

-- List all indexes on profiles table
SELECT 
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE tablename = 'profiles'
ORDER BY indexname;

-- Check table sizes and index usage
SELECT 
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size,
    pg_size_pretty(pg_indexes_size(schemaname||'.'||tablename)) AS index_size
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;

-- ================================================
-- NOTES:
-- 
-- 1. These indexes will significantly improve:
--    - Search queries (category, location, price filtering)
--    - User dashboard (my listings)
--    - Homepage (recent listings feed)
--    - Full-text search (Turkish language aware)
--
-- 2. Trade-offs:
--    - Indexes improve read performance
--    - Indexes slightly slow down write operations
--    - Indexes use disk space
--    - For PazarGlobal (read-heavy marketplace), this is ideal
--
-- 3. Monitoring:
--    - Monitor query performance after deploying indexes
--    - Use Supabase dashboard → Database → Query Performance
--    - Drop unused indexes if needed
--
-- 4. Maintenance:
--    - Supabase handles VACUUM and ANALYZE automatically
--    - For heavy traffic, consider manual ANALYZE weekly
-- ================================================
