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

def check_jurisdiction(target_country: str, reg_jurisdiction: str) -> bool:
    if not reg_jurisdiction or reg_jurisdiction == 'Global':
        return True
    if not target_country:
        return False
        
    t_lower = target_country.lower().strip()
    r_lower = reg_jurisdiction.lower().strip()
    
    if t_lower == r_lower or t_lower in r_lower or r_lower in t_lower:
        return True
        
    return False
