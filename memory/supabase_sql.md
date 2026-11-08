# Aplicar SQL no Supabase
Host direto (db.<ref>.supabase.co) é só IPv6 e não resolve aqui. Use o pooler:
psycopg2.connect(host='aws-1-sa-east-1.pooler.supabase.com', port=5432, user='postgres.<ref>', password=SUPABASE_SENHA, dbname='postgres', sslmode='require')
Termine o SQL com `NOTIFY pgrst, 'reload schema';` para a API REST enxergar tabelas novas.
