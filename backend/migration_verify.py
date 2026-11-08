"""
Verify OS data by loading in browser form (the reliable method)
vs what the JSON API returns
"""
import asyncio
from playwright.async_api import async_playwright

OLD_SYSTEM_URL = "https://gestao.mastermaqassistencia.com.br/app/index.php"
LOGIN_URL = "https://gestao.mastermaqassistencia.com.br/app/login.php"
EMAIL = "mastermaqassistencia@gmail.com"
PASSWORD = "atr132641"

FIELD_IDS = [
    'ose_id', 'nome', 'data_cadastro', 'data', 'cep', 'endereco',
    'bairro', 'cidade', 'uf', 'cel1', 'cel2', 'fixo', 'email',
    'taxa', 'ponto_ref', 'tipo_atendimento', 'produto', 'marca',
    'modelo', 'defeito', 'observacoes'
]

async def capture_fields(page):
    data = {}
    for fid in FIELD_IDS:
        val = await page.evaluate(f'document.getElementById("{fid}")?.value || ""')
        if val.strip():
            data[fid] = val.strip()
    return data

async def verify():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        # Login
        await page.goto(LOGIN_URL, wait_until="networkidle", timeout=30000)
        await page.fill('#inputEmail', EMAIL)
        await page.fill('#inputPassword', PASSWORD)
        await page.keyboard.press("Enter")
        await asyncio.sleep(3)
        
        test_numbers = [27577, 27576, 27575, 26220]
        
        for num in test_numbers:
            # Navigate fresh each time to avoid session contamination
            await page.goto(OLD_SYSTEM_URL, wait_until="networkidle", timeout=30000)
            await asyncio.sleep(2)
            
            # Type OS number and trigger data load via blur
            await page.click('#ose_id')
            await page.fill('#ose_id', '')
            await page.type('#ose_id', str(num), delay=50)
            await page.click('h3')  # blur
            await asyncio.sleep(6)
            
            data = await capture_fields(page)
            print(f"=== OS {num} (BROWSER FORM) ===")
            print(f"  nome: {data.get('nome', 'EMPTY')}")
            print(f"  produto: {data.get('produto', 'EMPTY')}")
            print(f"  marca: {data.get('marca', 'EMPTY')}")
            print(f"  modelo: {data.get('modelo', 'EMPTY')}")
            print(f"  defeito: {data.get('defeito', 'EMPTY')[:80]}")
            print()
        
        await browser.close()

asyncio.run(verify())
