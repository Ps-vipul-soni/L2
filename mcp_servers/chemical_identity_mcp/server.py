import re
import asyncio
import httpx
import sys
import os

# Add project root to sys.path to import backend schemas
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from backend.schemas.state_schemas import NormalizedIngredient

# Plain dictionary cache as requested
# Key: sanitized_name (str), Value: dict (normalized ingredient template)
_CACHE = {}

CAS_REGEX = re.compile(r'^\d{2,7}-\d{2}-\d$')

def sanitize_ingredient_name(raw_name: str) -> str:
    """Sanitize the input to remove noise like percentages, and standard symbols in parentheses."""
    name = raw_name
    # Strip "< 0.01%", "10%", "5 ppm", "100 mg/kg"
    name = re.sub(r'<?\s*\d+(?:\.\d+)?\s*(?:%|ppm|mg/kg)', '', name, flags=re.IGNORECASE)
    # Strip standalone chemical symbols like "(Cd)", "(Pb)"
    name = re.sub(r'\([A-Za-z0-9]+\)', '', name)
    # Cleanup commas and weird spacing
    name = name.replace(',', ' ').strip()
    name = re.sub(r'\s+', ' ', name)
    return name

async def fetch_with_retry(client: httpx.AsyncClient, url: str, max_retries: int = 5) -> httpx.Response:
    """Basic backoff retry for 429 Too Many Requests."""
    for attempt in range(max_retries):
        response = await client.get(url, follow_redirects=True)
        if response.status_code == 429:
            delay = 2 ** attempt
            print(f"PubChem 429 Throttled. Retrying in {delay} seconds...")
            await asyncio.sleep(delay)
            continue
        return response
    return response

async def resolve_ingredient(name: str) -> dict:
    """
    Resolve a chemical ingredient name or synonym to its canonical CAS number and PubChem CID.
    """
    raw_name = name
    sanitized_name = sanitize_ingredient_name(raw_name)
    
    if sanitized_name in _CACHE:
        print(f"CACHE HIT for '{sanitized_name}'")
        # Return a copy with the original raw_name to echo it back exactly
        cached_result = dict(_CACHE[sanitized_name])
        cached_result["raw_name"] = raw_name
        return cached_result
    
    is_cas = bool(CAS_REGEX.match(sanitized_name))
    
    # Base fallback unresolved result using NormalizedIngredient
    result = NormalizedIngredient(
        raw_name=raw_name,
        canonical_name=sanitized_name,  # requirement: fallback is the sanitized name, never null
        cas_number=None,
        pubchem_cid=None,
        resolution_method="unresolved"
    ).model_dump()
    
    async with httpx.AsyncClient() as client:
        # 1. Fetch CID via name lookup (PubChem supports CAS as 'name')
        cids_url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{sanitized_name}/cids/JSON"
        res = await fetch_with_retry(client, cids_url)
        
        if res.status_code == 200:
            try:
                data = res.json()
                cids = data.get('IdentifierList', {}).get('CID', [])
                if cids:
                    cid = str(cids[0])
                    result["pubchem_cid"] = cid
                    
                    # 2. Fetch canonical name via Title property
                    title_url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{cid}/property/Title/JSON"
                    title_res = await fetch_with_retry(client, title_url)
                    if title_res.status_code == 200:
                        props = title_res.json().get('PropertyTable', {}).get('Properties', [])
                        if props:
                            fetched_title = props[0].get('Title')
                            if fetched_title:
                                result["canonical_name"] = fetched_title
                    
                    # 3. Fetch synonyms to extract CAS (if not already exact CAS)
                    cas_number = sanitized_name if is_cas else None
                    if not cas_number:
                        syn_url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{cid}/synonyms/JSON"
                        syn_res = await fetch_with_retry(client, syn_url)
                        if syn_res.status_code == 200:
                            info = syn_res.json().get('InformationList', {}).get('Information', [])
                            if info:
                                synonyms = info[0].get('Synonym', [])
                                for syn in synonyms:
                                    if CAS_REGEX.match(syn):
                                        cas_number = syn
                                        break
                    
                    result = NormalizedIngredient(
                        raw_name=raw_name,
                        canonical_name=result["canonical_name"],
                        cas_number=cas_number,
                        pubchem_cid=cid,
                        resolution_method="exact_cas_match" if is_cas else "pubchem_synonym_lookup"
                    ).model_dump()
                    
            except Exception:
                pass # Graceful degradation back to 'unresolved'

    # Save to cache (only saving the core logic output)
    _CACHE[sanitized_name] = result
    
    return result
