from lxml import etree
from backend.schemas.state_schemas import DocumentExtractionResult, ExtractedComponent, ExtractedIngredient

def parse_fmd(document_path: str) -> DocumentExtractionResult:
    """Parses an XML FMD document using lxml, flattening the hierarchy."""
    try:
        tree = etree.parse(document_path)
        root = tree.getroot()
    except Exception as e:
        return DocumentExtractionResult(
            doc_type="FMD",
            product_name_hint=None,
            components=[],
            extraction_confidence=0.0,
            extraction_notes=f"Failed to parse XML: {str(e)}"
        )

    # Simple IPC-1752A style traversal: Product -> SubAssembly -> Material -> Substance
    components_map = {}
    
    # We will just traverse all nodes and look for Substance nodes, keeping track of ancestry.
    # Alternatively, specifically look for Substance tags and trace back up to Product.
    
    # Simple recursive function to extract substances with their hierarchical path
    def traverse(node, current_path):
        name = node.attrib.get("name", node.tag)
        path = current_path + [name] if current_path else [name]
        
        # If it's a leaf node representing a substance
        if node.tag.lower() == "substance" or "cas" in node.attrib:
            # We are at an ingredient level
            raw_name = node.attrib.get("name", "Unknown Substance")
            cas = node.attrib.get("cas", None)
            conc = node.attrib.get("concentration", None)
            unit = node.attrib.get("unit", None)
            
            if conc is not None:
                try:
                    conc = float(conc)
                except:
                    conc = None
                    
            # Component name is the ancestry up to this point (excluding the substance itself)
            comp_name = " / ".join(current_path) if current_path else "Main Product"
            
            ing = ExtractedIngredient(
                raw_name=raw_name,
                cas_number=cas,
                concentration_value=conc,
                concentration_unit=unit
            )
            
            if comp_name not in components_map:
                components_map[comp_name] = ExtractedComponent(component_name=comp_name, ingredients=[])
            components_map[comp_name].ingredients.append(ing)
            return

        for child in node:
            traverse(child, path)

    traverse(root, [])

    return DocumentExtractionResult(
        doc_type="FMD",
        product_name_hint=root.attrib.get("name", None),
        components=list(components_map.values()),
        extraction_confidence=0.9,
        extraction_notes="Deterministically parsed via lxml hierarchical flattening."
    )
