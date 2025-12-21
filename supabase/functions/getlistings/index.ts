import { serve } from "https://deno.land/std@0.168.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2.39.3";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
};

const redisUrl = Deno.env.get("UPSTASH_REDIS_REST_URL");
const redisToken = Deno.env.get("UPSTASH_REDIS_REST_TOKEN");
const redisTtlSeconds = Number(Deno.env.get("LISTINGS_CACHE_TTL")) || 60;

async function redisGet(key: string) {
  if (!redisUrl || !redisToken) return null;
  try {
    const res = await fetch(`${redisUrl}/get/${encodeURIComponent(key)}`, {
      headers: { Authorization: `Bearer ${redisToken}` },
    });
    if (!res.ok) return null;
    const json = await res.json();
    return json.result ? JSON.parse(json.result) : null;
  } catch (_err) {
    return null;
  }
}

async function redisSet(key: string, value: unknown, ttlSeconds: number) {
  if (!redisUrl || !redisToken) return;
  try {
    await fetch(`${redisUrl}/set/${encodeURIComponent(key)}/${encodeURIComponent(JSON.stringify(value))}`, {
      headers: { Authorization: `Bearer ${redisToken}` },
    });
    if (ttlSeconds > 0) {
      await fetch(`${redisUrl}/expire/${encodeURIComponent(key)}/${ttlSeconds}`, {
        headers: { Authorization: `Bearer ${redisToken}` },
      });
    }
  } catch (_err) {
    // ignore cache errors
  }
}

function boundLimit(raw: unknown, fallback = 20, max = 100) {
  const n = Number(raw);
  if (!Number.isFinite(n) || n <= 0) return fallback;
  return Math.min(Math.floor(n), max);
}

serve(async (req) => {
  if (req.method === "OPTIONS") {
    return new Response("ok", { headers: corsHeaders });
  }

  let body: any;
  try {
    body = await req.json();
  } catch (_err) {
    return new Response(
      JSON.stringify({ success: false, error: "Invalid JSON body", listings: [] }),
      { status: 400, headers: { ...corsHeaders, "Content-Type": "application/json" } },
    );
  }

  const { category = "all", search = "", limit = 20, cursor } = body || {};
  const safeLimit = boundLimit(limit);

  const cacheKey = `listings:${category}:${search}:${safeLimit}:${cursor || ""}`;

  const cached = await redisGet(cacheKey);
  if (cached) {
    return new Response(JSON.stringify(cached), {
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  }

  const supabaseUrl = Deno.env.get("SUPABASE_URL") ?? "";
  const supabaseKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ?? "";
  const bucket = Deno.env.get("PUBLIC_PRODUCT_BUCKET") ?? "product-images";
  const supabase = createClient(supabaseUrl, supabaseKey);

  let query = supabase
    .from("listings")
    .select("id,title,description,price,images,image_url,category,created_at,status")
    .eq("status", "active")
    .order("created_at", { ascending: false })
    .limit(safeLimit);

  if (category && category !== "all") {
    query = query.eq("category", category);
  }

  if (search && typeof search === "string" && search.trim()) {
    const term = search.trim();
    query = query.or(`title.ilike.%${term}%,description.ilike.%${term}%`);
  }

  if (cursor && typeof cursor === "string") {
    query = query.lt("created_at", cursor);
  }

  const { data: listings, error } = await query;

  if (error) {
    return new Response(
      JSON.stringify({ success: false, error: error.message, listings: [] }),
      { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } },
    );
  }

  const listingsWithImages = (listings || []).map((listing: any) => {
    let imageUrls: string[] = [];
    if (listing.images && Array.isArray(listing.images) && listing.images.length > 0) {
      imageUrls = listing.images.map((path: string) => `${supabaseUrl}/storage/v1/object/public/${bucket}/${path}`);
    } else if (listing.image_url) {
      imageUrls = [listing.image_url];
    }
    return {
      ...listing,
      image_urls: imageUrls,
      primary_image: imageUrls[0] || listing.image_url || null,
    };
  });

  const nextCursor = listingsWithImages.length === safeLimit
    ? listingsWithImages[listingsWithImages.length - 1]?.created_at
    : null;

  const responseBody = {
    success: true,
    listings: listingsWithImages,
    count: listingsWithImages.length,
    next_cursor: nextCursor,
  };

  await redisSet(cacheKey, responseBody, redisTtlSeconds);

  return new Response(JSON.stringify(responseBody), {
    headers: { ...corsHeaders, "Content-Type": "application/json" },
  });
});
