-- Taxa de visita paga armazenada em coluna própria + OSs do site sem texto do site em Observações.
-- Aplicado em 23/10/2026. O site escreve direto no Supabase, por isso a regra fica num trigger.
ALTER TABLE service_orders ADD COLUMN IF NOT EXISTS visit_fee_paid boolean NOT NULL DEFAULT false;
ALTER TABLE service_orders ADD COLUMN IF NOT EXISTS site_info text NOT NULL DEFAULT '';

CREATE OR REPLACE FUNCTION service_orders_site_obs() RETURNS trigger AS $$
DECLARE
  ln text;
  kept text[] := '{}';
BEGIN
  IF NEW.source = 'external_site' AND coalesce(NEW.observations, '') <> '' THEN
    FOR ln IN SELECT regexp_split_to_table(NEW.observations, E'\n') LOOP
      IF ln ILIKE '%[SITE]%Taxa de visita PAGA%' THEN
        NEW.visit_fee_paid := true;
      END IF;
      IF ln ILIKE 'Tipo de serviço:%' OR ln ILIKE '%Tipo de serviço:%Origem: site%' OR ln ILIKE '[SITE]%' THEN
        IF position(ln IN coalesce(NEW.site_info, '')) = 0 THEN
          NEW.site_info := trim(both E'\n' FROM coalesce(NEW.site_info, '') || E'\n' || ln);
        END IF;
      ELSIF trim(ln) <> '' THEN
        kept := kept || ln;
      END IF;
    END LOOP;
    NEW.observations := array_to_string(kept, E'\n');
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_service_orders_site_obs ON service_orders;
CREATE TRIGGER trg_service_orders_site_obs BEFORE INSERT OR UPDATE ON service_orders
  FOR EACH ROW EXECUTE FUNCTION service_orders_site_obs();

-- Backfill: dispara o trigger nas OSs do site que ainda têm texto em Observações.
UPDATE service_orders SET observations = observations WHERE source = 'external_site' AND coalesce(observations, '') <> '';
