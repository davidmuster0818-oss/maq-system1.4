-- Products: add image_url and product_type columns
--
-- Context: added 31/07/2026 to support the "Imagem do Produto" and
-- "Tipo de Produto" (Geladeira, Coifa, Fogão, ...) fields in the
-- ProductFormModal.
--
-- Until you run this migration, the backend stores these two fields in a
-- Mongo sidecar collection `product_metadata` and merges them at read
-- time. The API contract is unchanged — clients see `image_url` and
-- `product_type` on every product regardless. Running this migration lets
-- Supabase itself become the s
ingle source of truth and lets `image_url`
-- be indexed/queried like any other Supabase column.
--
-- After you run this, the sidecar keeps working (as a redundant fallback)
-- but new writes will flow to Supabase natively.
--
-- To run: open the Supabase Dashboard → SQL Editor → paste this file →
--         click "Run". No downtime.

ALTER TABLE public.products
  ADD COLUMN IF NOT EXISTS image_url TEXT DEFAULT '',
  ADD COLUMN IF NOT EXISTS product_type TEXT DEFAULT '';

-- Optional: light index if you plan to filter/search by product_type
-- (e.g. "show me all Geladeiras").
CREATE INDEX IF NOT EXISTS idx_products_product_type
  ON public.products (product_type)
  WHERE product_type IS NOT NULL AND product_type <> '';

-- Storage bucket for product images.
-- The backend endpoint POST /api/inventory/upload-image creates this on
-- first use, but running it explicitly here documents the intent.
INSERT INTO storage.buckets (id, name, public)
VALUES ('product-images', 'product-images', true)
ON CONFLICT (id) DO NOTHING;

-- Public read policy for product-images (so QR pages can render photos
-- without a signed URL). Write policy stays service-role-only.
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'storage' AND tablename = 'objects'
      AND policyname = 'product_images_public_read'
  ) THEN
    CREATE POLICY product_images_public_read
      ON storage.objects FOR SELECT
      USING (bucket_id = 'product-images');
  END IF;
END $$;
