def check_string_match(target: str, valid_list: list) -> bool:
    if not valid_list:
        return True
    if not target:
        return False
    
    # 1. Exact match
    if target in valid_list:
        return True
        
    target_lower = target.lower().strip()
    valid_lower = [v.lower().strip() for v in valid_list]
    
    # 2. Case-insensitive exact / normalized
    if target_lower in valid_lower:
        return True
        
    # 3. Substring
    for v in valid_lower:
        if target_lower in v or v in target_lower:
            return True
            
    return False

def normalize_jurisdiction(target: str) -> str:
    """Deterministically normalizes valid jurisdictions into their canonical database equivalents."""
    if not target:
        return ""
    
    t_lower = target.lower().strip()
    
    # US normalizations
    if t_lower in ["us", "usa", "united states", "united states of america"]:
        return "US"
        
    # US-CA normalizations
    if t_lower in ["us-ca", "california", "ca", "california, usa"]:
        return "US-CA"
        
    # EU normalizations
    if t_lower in ["eu", "european union"]:
        return "EU"
        
    return target.strip()

def check_jurisdiction(target_country: str, reg_jurisdiction: str) -> bool:
    if not reg_jurisdiction or reg_jurisdiction == 'Global':
        return True
    if not target_country:
        return False
        
    normalized_target = normalize_jurisdiction(target_country)
    normalized_reg = normalize_jurisdiction(reg_jurisdiction)
    
    return normalized_target == normalized_reg
