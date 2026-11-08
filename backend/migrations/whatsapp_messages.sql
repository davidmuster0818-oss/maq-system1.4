-- Histórico de mensagens WhatsApp (envios, recebidas e status). Faltava no Supabase.
CREATE TABLE IF NOT EXISTS whatsapp_messages (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  direction text,
  to_number text,
  from_number text,
  contact_name text,
  type text,
  body text,
  media_id text,
  os_number text,
  wa_message_id text,
  status text,
  ok boolean,
  ts text,
  sent_at text,
  received_at text,
  status_updated_at text,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS whatsapp_messages_wa_id ON whatsapp_messages (wa_message_id);
ALTER TABLE whatsapp_messages ENABLE ROW LEVEL SECURITY;
NOTIFY pgrst, 'reload schema';
