from .sds_parser import parse_sds
from .bom_parser import parse_bom
from .fmd_parser import parse_fmd

PARSER_REGISTRY = {
    ".pdf": parse_sds,
    ".csv": parse_bom,
    ".xls": parse_bom,
    ".xlsx": parse_bom,
    ".xml": parse_fmd
}
