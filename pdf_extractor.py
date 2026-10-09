"""
Extract electrical specifications from technical PDF datasheets.
Supports any brand of solar panel, inverter/VFD, and motor.
Uses text extraction + regex pattern matching on standardized electrical terms.
"""

import re
import io
import pdfplumber
from dataclasses import dataclass, field
from typing import Optional, List, Tuple


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def _ocr_available() -> bool:
    """Check if OCR dependencies are installed."""
    try:
        import pytesseract
        from pdf2image import convert_from_bytes
        return True
    except ImportError:
        return False


def _ocr_extract(pdf_bytes: bytes, max_pages: int = 10) -> str:
    """Extract text via OCR (for image-based PDFs)."""
    import pytesseract
    from pdf2image import convert_from_bytes
    images = convert_from_bytes(pdf_bytes, dpi=300, last_page=max_pages)
    parts = []
    for img in images:
        parts.append(pytesseract.image_to_string(img))
    return "\n".join(parts)


def extract_text_from_pdf(pdf_bytes: bytes, max_pages: int = 10) -> str:
    """Extract all text from a PDF. Falls back to OCR if text layer is empty."""
    text_parts = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for i, page in enumerate(pdf.pages[:max_pages]):
            page_text = page.extract_text() or ""
            text_parts.append(page_text)
            tables = page.extract_tables()
            for table in tables:
                for row in table:
                    if row:
                        cleaned = [str(cell).strip() if cell else "" for cell in row]
                        text_parts.append(" | ".join(cleaned))

    combined = "\n".join(text_parts).strip()

    # If very little text was extracted, try OCR
    if len(combined) < 100 and _ocr_available():
        combined = _ocr_extract(pdf_bytes, max_pages)

    return combined


def find_number(text: str, patterns: List[str], default=None,
                value_range: Tuple[float, float] = None) -> Optional[float]:
    """
    Search for a numeric value matching any of the given regex patterns.
    patterns should have a named group 'val' for the number.
    If value_range is given, only accept values within that range.
    """
    for pattern in patterns:
        matches = re.finditer(pattern, text, re.IGNORECASE | re.MULTILINE)
        for m in matches:
            try:
                raw = m.group('val')
                # Handle comma as decimal separator
                raw = raw.replace(',', '.').replace(' ', '')
                val = float(raw)
                if value_range:
                    if value_range[0] <= val <= value_range[1]:
                        return val
                else:
                    return val
            except (ValueError, IndexError):
                continue
    return default


def find_text(text: str, patterns: List[str], default: str = "") -> str:
    """Search for a text value matching patterns."""
    for pattern in patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            try:
                return m.group('val').strip()
            except (IndexError, AttributeError):
                return m.group(0).strip()
    return default


# ──────────────────────────────────────────────
# Panel extraction
# ──────────────────────────────────────────────

@dataclass
class ExtractedPanelSpecs:
    model: str = ""
    pmax_w: Optional[float] = None
    voc_v: Optional[float] = None
    vmp_v: Optional[float] = None
    isc_a: Optional[float] = None
    imp_a: Optional[float] = None
    coeff_voc_pct: Optional[float] = None
    coeff_isc_pct: Optional[float] = None
    coeff_pmax_pct: Optional[float] = None
    noct_c: Optional[float] = None
    bifacial: bool = False
    bifaciality_pct: Optional[float] = None
    max_system_voltage: Optional[float] = None
    max_series_fuse_a: Optional[float] = None
    power_tolerance_pct: Optional[float] = None
    raw_text: str = ""
    all_pmax_values: list = field(default_factory=list)
    confidence: float = 0.0


def _extract_stc_table_row(text: str, target_pmax: Optional[float] = None
                           ) -> dict:
    """
    Try to find an STC table in the OCR text and extract a row.
    Multi-variant datasheets have rows like:
        445  450  455  460  465  470    (Pmax)
        49.56 49.70 49.85 50.01 50.15 50.31  (Voc)
    Returns dict with pmax, voc, vmp, isc, imp for the selected column.
    """
    result = {}
    # Look for the STC table block
    stc_block = re.search(
        r'(?:ELECTRICAL\s+PARAMETERS\s+AT\s+STC|PARAMETRES?\s+ELECTRIQUES?\s+STC)'
        r'(.*?)(?:ELECTRICAL|PARAMETRES?|CHARACTERISTICS|OPERATING|$)',
        text, re.IGNORECASE | re.DOTALL
    )
    if not stc_block:
        return result

    block = stc_block.group(1)
    lines = [l.strip() for l in block.split('\n') if l.strip()]

    # Try to find the Pmax row (the one with power values 100-900W)
    pmax_row = None
    param_rows = {}  # label -> list of numbers

    for line in lines:
        # Extract all numbers from the line
        nums = re.findall(r'(\d+[\.,]\d+|\d{2,4})', line)
        float_nums = []
        for n in nums:
            try:
                float_nums.append(float(n.replace(',', '.')))
            except ValueError:
                pass

        # Filter to reasonable electrical values (skip years, dimensions, etc.)
        line_lower = line.lower()

        if ('pmax' in line_lower or 'maximum power' in line_lower or
                'rated' in line_lower and 'power' in line_lower) and not pmax_row:
            pmax_candidates = [n for n in float_nums if 100 <= n <= 900]
            if len(pmax_candidates) >= 2:
                pmax_row = pmax_candidates
                param_rows['pmax'] = pmax_candidates
        elif 'voc' in line_lower or 'open circuit' in line_lower:
            voc_candidates = [n for n in float_nums if 10 <= n <= 100]
            if len(voc_candidates) >= 2:
                param_rows['voc'] = voc_candidates
        elif ('vmp' in line_lower or 'vmpp' in line_lower or
              'maximum power voltage' in line_lower):
            vmp_candidates = [n for n in float_nums if 8 <= n <= 80]
            if len(vmp_candidates) >= 2:
                param_rows['vmp'] = vmp_candidates
        elif 'isc' in line_lower or 'short circuit' in line_lower:
            isc_candidates = [n for n in float_nums if 1 <= n <= 30]
            if len(isc_candidates) >= 2:
                param_rows['isc'] = isc_candidates
        elif ('imp' in line_lower or 'impp' in line_lower or
              'maximum power current' in line_lower):
            imp_candidates = [n for n in float_nums if 1 <= n <= 25]
            if len(imp_candidates) >= 2:
                param_rows['imp'] = imp_candidates

    if not pmax_row or not param_rows.get('voc'):
        return result

    # Determine which column to use
    n_cols = len(pmax_row)
    col_idx = n_cols - 1  # default: last (highest power)

    if target_pmax is not None:
        # Find closest match
        diffs = [abs(p - target_pmax) for p in pmax_row]
        col_idx = diffs.index(min(diffs))

    result['pmax'] = pmax_row[col_idx] if col_idx < len(pmax_row) else None

    for key in ['voc', 'vmp', 'isc', 'imp']:
        vals = param_rows.get(key, [])
        if col_idx < len(vals):
            result[key] = vals[col_idx]

    return result


def extract_panel_specs(pdf_bytes: bytes,
                        target_pmax: Optional[float] = None) -> ExtractedPanelSpecs:
    """
    Extract solar panel specifications from a PDF datasheet.
    Works with any brand. Supports multi-variant datasheets.
    target_pmax: if set, select the column closest to this power in multi-variant tables.
    """
    text = extract_text_from_pdf(pdf_bytes)
    result = ExtractedPanelSpecs(raw_text=text)

    # --- Model name ---
    # Generic: find alphanumeric model codes (brand-agnostic)
    model_patterns = [
        r'(?P<val>JAM\w+[-/]\w+)',           # JA Solar
        r'(?P<val>CS[\d]\w+[-]\w+)',          # Canadian Solar
        r'(?P<val>TSM[-]\w+)',                # Trina Solar
        r'(?P<val>LR\d+[-]\w+)',              # LONGi
        r'(?P<val>JKM\w+[-/]\w+)',            # Jinko Solar
        r'(?P<val>RSM\w+[-]\w+)',             # Risen
        r'(?P<val>DHM[-]?\w+)',               # DAH Solar
        r'(?P<val>HiKu\w*[-]\w+)',            # Canadian HiKu
        r'(?P<val>Tiger\s*Neo\s*\w+)',        # Jinko Tiger
        r'(?P<val>Hi-MO\s*\w+)',              # LONGi Hi-MO
        r'(?P<val>VERTEX\s*\w+)',             # Trina Vertex
        r'(?P<val>RE\w+[-]\w+)',              # Risen
        r'(?P<val>STP\w+[-]\w+)',             # SunTech
        r'(?P<val>PHK\w+[-]\w+)',             # Phono Solar
        r'(?P<val>ZN\w+[-]\w+)',              # ZNShine
        r'(?P<val>[A-Z]{2,5}\d{2,}\w*[-/]\w+)',  # Generic: 2-5 uppercase + digits
        r'(?:model|modele|type)\s*[:\|]?\s*(?P<val>[\w][\w\-/]+\w)',
    ]
    result.model = find_text(text, model_patterns) or "Unknown Panel"

    # --- Detect bifacial ---
    bifacial_keywords = r'bifacial|bi-facial|double.?glass|double.?verre|bi.?face'
    result.bifacial = bool(re.search(bifacial_keywords, text, re.IGNORECASE))

    # --- Try structured table extraction first ---
    table_data = _extract_stc_table_row(text, target_pmax)

    # --- Pmax ---
    # Collect all Pmax from the STC table Pmax row (the reliable source)
    pmax_patterns = [
        r'(?:rated\s+)?(?:maximum\s+)?power\s*\(?\s*Pmax\s*\)?\s*\[?W\]?\s*[:\|]?\s*(?P<val>\d{3}[\.,]?\d*)',
        r'Pmax\s*\)?\s*\[?W\]?\s*[:\|]?\s*(?P<val>\d{3}[\.,]?\d*)',
    ]
    all_pmax = set()
    for pat in pmax_patterns:
        for m in re.finditer(pat, text, re.IGNORECASE):
            try:
                val = float(m.group('val').replace(',', '.'))
                if 100 <= val <= 900:
                    all_pmax.add(val)
            except (ValueError, IndexError):
                pass
    # Also add from table extraction
    if 'pmax' in table_data:
        stc_pmax_row = re.search(
            r'(?:rated\s+)?(?:max\w+\s+)?power.*?(?:Pmax).*?\n\s*'
            r'((?:\d{3}[\.,]?\d?\s+){2,})',
            text, re.IGNORECASE
        )
        # Add values from the structured table
        all_pmax.add(table_data['pmax'])

    result.all_pmax_values = sorted([p for p in all_pmax if 100 <= p <= 900], reverse=True)
    result.pmax_w = table_data.get('pmax') or (result.all_pmax_values[0] if result.all_pmax_values else None)

    # --- Voc, Vmp, Isc, Imp: prefer table data, fallback to regex ---
    result.voc_v = table_data.get('voc') or find_number(text, [
        r'(?:open\s+circuit\s+voltage|tension\s+circuit\s+ouvert)\s*\(?\s*Voc\s*\)?\s*\[?V\]?\s*[:\|]?\s*(?P<val>\d+[\.,]\d+)',
        r'Voc\s*\)?\s*\[?V\]?\s*[:\|]?\s*(?P<val>\d+[\.,]\d+)',
    ], value_range=(10, 100))

    result.vmp_v = table_data.get('vmp') or find_number(text, [
        r'(?:max\w*\s+power\s+voltage)\s*\(?\s*Vmp[p]?\s*\)?\s*\[?V\]?\s*[:\|]?\s*(?P<val>\d+[\.,]\d+)',
        r'Vmp[p]?\s*\)?\s*\[?V\]?\s*[:\|]?\s*(?P<val>\d+[\.,]\d+)',
    ], value_range=(8, 80))

    result.isc_a = table_data.get('isc') or find_number(text, [
        r'(?:short\s+circuit\s+current)\s*\(?\s*Isc\s*\)?\s*\[?A\]?\s*[:\|]?\s*(?P<val>\d+[\.,]\d+)',
        r'Isc\s*\)?\s*\[?A\]?\s*[:\|]?\s*(?P<val>\d+[\.,]\d+)',
    ], value_range=(1, 30))

    result.imp_a = table_data.get('imp') or find_number(text, [
        r'(?:max\w*\s+power\s+current)\s*\(?\s*Imp[p]?\s*\)?\s*\[?A\]?\s*[:\|]?\s*(?P<val>\d+[\.,]\d+)',
        r'Imp[p]?\s*\)?\s*\[?A\]?\s*[:\|]?\s*(?P<val>\d+[\.,]\d+)',
    ], value_range=(1, 25))

    # --- Temperature coefficients ---
    result.coeff_voc_pct = find_number(text, [
        r'Voc\s*\(?[βBb]_?Voc\)?\s*[:\|]?\s*(?P<val>-?\d+[\.,]\d+)\s*%',
        r'[βBb]_?Voc\s*\)?\s*[:\|]?\s*(?P<val>-?\d+[\.,]\d+)\s*%',
        r'(?:coeff\w*\s+.*?Voc|Voc.*?coeff\w*)\s*[:\|]?\s*(?P<val>-0[\.,]\d+)\s*%',
        r'(?P<val>-0[\.,]2[0-9]{1,2})\s*%\s*/\s*[°o]?\s*C',  # -0.2XX %/°C
        r'(?P<val>-0[\.,]3[0-9]{1,2})\s*%\s*/\s*[°o]?\s*C',
    ], value_range=(-0.5, -0.1))

    result.coeff_isc_pct = find_number(text, [
        r'Isc\s*\(?[αAa]_?Isc\)?\s*[:\|]?\s*(?P<val>\+?\d+[\.,]\d+)\s*%',
        r'[αAa]_?Isc\s*\)?\s*[:\|]?\s*(?P<val>\+?\d+[\.,]\d+)\s*%',
        r'(?:coeff\w*\s+.*?Isc|Isc.*?coeff\w*)\s*[:\|]?\s*(?P<val>\+?0[\.,]0\d+)\s*%',
        r'(?P<val>\+?0[\.,]0[3-6]\d?)\s*%\s*/\s*[°o]?\s*C',  # +0.0XX %/°C
    ], value_range=(0.01, 0.10))

    result.coeff_pmax_pct = find_number(text, [
        r'Pmax\s*\(?[γYy]_?Pm[ap]\w*\)?\s*[:\|]?\s*(?P<val>-?\d+[\.,]\d+)\s*%',
        r'[γYy]_?Pm[ap]\w*\s*\)?\s*[:\|]?\s*(?P<val>-?\d+[\.,]\d+)\s*%',
        r'(?:coeff\w*\s+.*?Pmax|Pmax.*?coeff\w*)\s*[:\|]?\s*(?P<val>-0[\.,]\d+)\s*%',
        r'(?:coeff\w*\s+.*?Pmp|Pmp.*?coeff\w*)\s*[:\|]?\s*(?P<val>-0[\.,]\d+)\s*%',
        r'(?P<val>-0[\.,][23][0-9]{1,2})\s*%\s*/?\s*[°o]?\s*C',
    ], value_range=(-0.6, -0.1))

    # --- NOCT ---
    result.noct_c = find_number(text, [
        r'NOCT\s*[:\|]?\s*(?P<val>\d+)\s*[°±]',
        r'NOCT\s*[:\|]?\s*(?P<val>\d+[\.,]?\d*)\s*[°±]?\s*[0-9]*\s*[°.]?\s*C',
        r'NOCT\s+(?P<val>4[0-9])',  # NOCT 45
        r'(?:nominal\s+operating\s+cell\s+temp)\w*\s*[:\|]?\s*(?P<val>\d+)',
        r'TONC\s*[:\|]?\s*(?P<val>\d+)',
    ], value_range=(38, 52))
    if result.noct_c is None:
        result.noct_c = 45.0  # safe default

    # --- Bifaciality ---
    if result.bifacial:
        result.bifaciality_pct = find_number(text, [
            r'[Bb]ifacialit[yé]\s*[:\|]?\s*(?P<val>\d+)\s*%',
            r'[Bb]ifacial\s+factor\s*[:\|]?\s*(?P<val>\d+)\s*%',
            r'(?P<val>[78]\d)\s*%\s*[±]\s*\d+\s*%',
        ], value_range=(50, 95))
        if result.bifaciality_pct is None:
            result.bifaciality_pct = 80.0

    # --- Max system voltage ---
    result.max_system_voltage = find_number(text, [
        r'[Mm]ax\w*\s+[Ss]ystem\s+[Vv]oltage\s*[:\|]?\s*(?P<val>\d{3,4})\s*V',
        r'(?P<val>1[05]00)\s*V\s*DC',
    ], value_range=(600, 1500))

    # --- Max series fuse ---
    result.max_series_fuse_a = find_number(text, [
        r'[Mm]ax\w*\s+[Ss]eries\s+[Ff]use\s+[Rr]ating\s*[:\|]?\s*(?P<val>\d+)\s*A',
        r'[Ff]use\s+[Rr]ating\s*[:\|]?\s*(?P<val>\d+)\s*A',
        r'[Ff]usible\s+max\s*[:\|]?\s*(?P<val>\d+)\s*A',
    ], value_range=(5, 50))

    # --- Power tolerance ---
    result.power_tolerance_pct = find_number(text, [
        r'[Pp]ower\s+[Tt]olerance\s*[:\|]?\s*0?\s*~?\s*\+\s*(?P<val>\d+)\s*[W%]',
    ], value_range=(0, 10))

    # --- Confidence score ---
    found = sum(1 for v in [
        result.pmax_w, result.voc_v, result.vmp_v, result.isc_a, result.imp_a,
        result.coeff_voc_pct, result.coeff_isc_pct, result.coeff_pmax_pct, result.noct_c
    ] if v is not None)
    result.confidence = found / 9.0

    return result


# ──────────────────────────────────────────────
# Inverter extraction
# ──────────────────────────────────────────────

@dataclass
class ExtractedInverterSpecs:
    model: str = ""
    power_kw: Optional[float] = None
    vdc_max: Optional[float] = None
    vdc_range_min: Optional[float] = None
    vdc_range_max: Optional[float] = None
    vdc_mpp: Optional[float] = None
    vdc_start: Optional[float] = None
    vdc_min_work: Optional[float] = None
    input_current_nominal: Optional[float] = None
    input_current_max: Optional[float] = None
    output_current_nominal: Optional[float] = None
    raw_text: str = ""
    all_models: list = field(default_factory=list)
    confidence: float = 0.0


def extract_inverter_specs(pdf_bytes: bytes, max_pages: int = 20) -> ExtractedInverterSpecs:
    """Extract inverter/VFD specifications from a PDF datasheet."""
    text = extract_text_from_pdf(pdf_bytes, max_pages=max_pages)
    result = ExtractedInverterSpecs(raw_text=text)

    # --- Model name ---
    model_patterns = [
        r'(?P<val>GD\d+[-]\w+[-]PV)',                     # INVT
        r'(?P<val>ATV\d+\w+)',                             # Schneider Altivar
        r'(?P<val>VFS\d+[-]\w+)',                          # Toshiba
        r'(?P<val>FR[-]?\w+\d+)',                          # Mitsubishi
        r'(?P<val>CFW\d+\w*)',                             # WEG
        r'(?P<val>HYDRO\w+[-]\w+)',                        # Nastec
        r'(?P<val>SP\d+[-]?\w+)',                          # Various solar pump inverters
        r'(?P<val>PSk\d+\w*)',                             # Lorentz
        r'(?:model|modele)\s*:?\s*(?P<val>[\w][\w\-/]+)',
    ]
    result.model = find_text(text, model_patterns) or "Unknown Inverter"

    # Find all model variants (for multi-model catalogs)
    all_models = set()
    for pat in model_patterns[:2]:
        for m in re.finditer(pat, text, re.IGNORECASE):
            all_models.add(m.group('val'))
    result.all_models = sorted(all_models)

    # --- Rated power ---
    result.power_kw = find_number(text, [
        r'(?:rated\s+)?(?:output\s+)?power\s*[:\|]?\s*(?P<val>\d+[\.,]?\d*)\s*kW',
        r'(?:puissance\s+)?(?:nominale|sortie)\s*[:\|]?\s*(?P<val>\d+[\.,]?\d*)\s*kW',
        r'(?P<val>\d+[\.,]?\d*)\s*kW\s+(?:solar|solaire|pump)',
    ], value_range=(0.3, 500))

    # --- DC voltage specs ---
    result.vdc_max = find_number(text, [
        r'max\.?\s*DC\s*(?:bus\s+)?voltage\s*[:\|]?\s*(?P<val>\d+)',
        r'(?:tension|voltage)\s+DC\s+max\s*[:\|]?\s*(?P<val>\d+)',
        r'max\.?\s*(?:input\s+)?voltage\s*[:\|]?\s*(?P<val>\d+)\s*V?\s*DC',
        r'DC\s+max\s*[:\|]?\s*(?P<val>\d+)\s*V',
    ], value_range=(200, 1500))

    # DC range
    # Try "300-750" or "300~750" or "300 to 750" pattern
    range_match = re.search(
        r'(?:recommended|recommand[eé]e?)\s*(?:DC\s+)?(?:input\s+)?voltage\s+range\s*[:\|]?\s*'
        r'(?P<min>\d+)\s*[-~toà]+\s*(?P<max>\d+)',
        text, re.IGNORECASE
    )
    if range_match:
        result.vdc_range_min = float(range_match.group('min'))
        result.vdc_range_max = float(range_match.group('max'))
    else:
        # Try separate patterns
        result.vdc_range_min = find_number(text, [
            r'(?:lowest|minimum)\s+(?:working\s+)?voltage\s*[:\|]?\s*(?P<val>\d+)',
            r'(?:tension|voltage)\s+min\w*\s*[:\|]?\s*(?P<val>\d+)',
        ], value_range=(100, 500))

        result.vdc_range_max = find_number(text, [
            r'(?:recommended|recommand[eé])\s*(?:max\w*)?\s*(?:input\s+)?voltage\s*[:\|]?\s*(?P<val>\d+)',
        ], value_range=(300, 1200))

    # MPP voltage
    result.vdc_mpp = find_number(text, [
        r'(?:recommended\s+)?MPP\s+voltage\s*[:\|]?\s*(?P<val>\d+)',
        r'MPPT\s+(?:voltage\s+)?range.*?(?P<val>\d{3})',
        r'MPP\s*[:\|]?\s*(?P<val>\d+)\s*V',
    ], value_range=(100, 1000))

    # Start-up voltage
    result.vdc_start = find_number(text, [
        r'start[- ]?up\s+voltage\s*[:\|]?\s*(?P<val>\d+)',
        r'tension\s+d[eé]marrage\s*[:\|]?\s*(?P<val>\d+)',
    ], value_range=(100, 500))

    # Min working voltage
    result.vdc_min_work = find_number(text, [
        r'lowest\s+working\s+voltage\s*[:\|]?\s*(?P<val>\d+)',
        r'(?:tension|voltage)\s+min\w*\s+(?:de\s+)?(?:travail|fonctionnement)\s*[:\|]?\s*(?P<val>\d+)',
    ], value_range=(50, 400))

    # --- Current specs ---
    result.input_current_nominal = find_number(text, [
        r'rated\s+(?:DC\s+)?input\s+current\s*[:\|]?\s*(?P<val>\d+[\.,]?\d*)',
        r'courant\s+entr[eé]e\s+nominal\s*[:\|]?\s*(?P<val>\d+[\.,]?\d*)',
        r'(?:nominal|rated)\s+input.*?(?P<val>\d+[\.,]?\d*)\s*A',
    ], value_range=(1, 1000))

    result.input_current_max = find_number(text, [
        r'max\.?\s*(?:DC\s+)?input\s+current\s*[:\|]?\s*(?P<val>\d+[\.,]?\d*)',
        r'courant\s+entr[eé]e\s+max\s*[:\|]?\s*(?P<val>\d+[\.,]?\d*)',
        r'max\w*\s+(?:DC\s+)?input.*?(?P<val>\d+[\.,]?\d*)\s*A',
    ], value_range=(1, 1000))

    result.output_current_nominal = find_number(text, [
        r'rated\s+output\s+current\s*[:\|]?\s*(?P<val>\d+[\.,]?\d*)',
        r'courant\s+sortie\s+nominal\s*[:\|]?\s*(?P<val>\d+[\.,]?\d*)',
        r'(?:nominal|rated)\s+output.*?(?P<val>\d+[\.,]?\d*)\s*A',
    ], value_range=(1, 1000))

    # --- Confidence ---
    found = sum(1 for v in [
        result.power_kw, result.vdc_max, result.vdc_range_max,
        result.input_current_nominal, result.input_current_max,
        result.output_current_nominal
    ] if v is not None)
    result.confidence = found / 6.0

    return result


# ──────────────────────────────────────────────
# Motor extraction
# ──────────────────────────────────────────────

@dataclass
class ExtractedMotorSpecs:
    model: str = ""
    power_kw: Optional[float] = None
    current_a: Optional[float] = None
    voltage_v: Optional[float] = None
    phases: int = 3
    speed_rpm: Optional[float] = None
    efficiency: Optional[float] = None
    cos_phi: Optional[float] = None
    raw_text: str = ""
    confidence: float = 0.0


def extract_motor_specs(pdf_bytes: bytes) -> ExtractedMotorSpecs:
    """Extract motor specifications from a PDF datasheet."""
    text = extract_text_from_pdf(pdf_bytes)
    result = ExtractedMotorSpecs(raw_text=text)

    # --- Model ---
    result.model = find_text(text, [
        r'(?:model|modele|type|ref)\s*[:\|]?\s*(?P<val>[\w][\w\-/]+)',
    ]) or "Unknown Motor"

    # --- Power ---
    result.power_kw = find_number(text, [
        r'(?:rated\s+)?(?:output\s+)?power\s*[:\|]?\s*(?P<val>\d+[\.,]?\d*)\s*kW',
        r'(?:puissance\s+)?(?:nominale|utile)\s*[:\|]?\s*(?P<val>\d+[\.,]?\d*)\s*kW',
        r'P[n2]?\s*[=:]\s*(?P<val>\d+[\.,]?\d*)\s*kW',
        r'(?P<val>\d+[\.,]?\d*)\s*kW\b',
    ], value_range=(0.1, 500))

    # --- Rated current ---
    result.current_a = find_number(text, [
        r'(?:rated|nominal)\s+current\s*[:\|]?\s*(?P<val>\d+[\.,]?\d*)\s*A',
        r'(?:courant\s+)?nominal\s*[:\|]?\s*(?P<val>\d+[\.,]?\d*)\s*A',
        r'I[n]?\s*[=:]\s*(?P<val>\d+[\.,]?\d*)\s*A',
        r'(?P<val>\d+[\.,]?\d*)\s*A\b',
    ], value_range=(0.5, 1000))

    # --- Voltage ---
    result.voltage_v = find_number(text, [
        r'(?:rated\s+)?voltage\s*[:\|]?\s*(?P<val>\d+)\s*V',
        r'(?:tension\s+)?nominale\s*[:\|]?\s*(?P<val>\d+)\s*V',
        r'(?P<val>380|400|415|440|460|480|690)\s*V',
        r'(?P<val>220|230|240)\s*V',
    ], value_range=(100, 1000))

    # --- Phases ---
    if re.search(r'(?:3\s*phase|triphas|3~|3ph)', text, re.IGNORECASE):
        result.phases = 3
    elif re.search(r'(?:1\s*phase|monophas|1~|1ph)', text, re.IGNORECASE):
        result.phases = 1

    # --- Speed ---
    result.speed_rpm = find_number(text, [
        r'(?:rated\s+)?speed\s*[:\|]?\s*(?P<val>\d{3,4})\s*(?:rpm|tr/min)',
        r'(?:vitesse\s+)?nominale\s*[:\|]?\s*(?P<val>\d{3,4})\s*(?:rpm|tr/min)',
        r'(?P<val>\d{3,4})\s*(?:rpm|tr/min)',
    ], value_range=(500, 4000))

    # --- Efficiency ---
    result.efficiency = find_number(text, [
        r'(?:efficiency|rendement)\s*[:\|]?\s*(?P<val>\d+[\.,]?\d*)\s*%',
        r'[ηn]\s*[=:]\s*(?P<val>\d+[\.,]?\d*)\s*%',
    ], value_range=(50, 99))

    # --- Power factor ---
    result.cos_phi = find_number(text, [
        r'(?:power\s+factor|cos\s*[φϕ])\s*[:\|=]?\s*(?P<val>0[\.,]\d+)',
        r'(?:facteur\s+de\s+puissance)\s*[:\|]?\s*(?P<val>0[\.,]\d+)',
    ], value_range=(0.5, 1.0))

    # --- Confidence ---
    found = sum(1 for v in [result.power_kw, result.current_a, result.voltage_v] if v is not None)
    result.confidence = found / 3.0

    return result


# ──────────────────────────────────────────────
# Inverter catalog: extract specs for a specific model
# ──────────────────────────────────────────────

def extract_inverter_for_model(pdf_bytes: bytes, target_power_kw: float,
                                max_pages: int = 20) -> ExtractedInverterSpecs:
    """
    For multi-model catalogs, try to extract specs for a specific power rating.
    Searches tables and text blocks near the target power value.
    """
    text = extract_text_from_pdf(pdf_bytes, max_pages=max_pages)
    result = ExtractedInverterSpecs(raw_text=text)

    # Find all model-power associations
    # Look for patterns like "GD100-022G-4-PV ... 22 ... kW"
    # Or table rows with power values

    # First try the generic extraction
    generic = extract_inverter_specs(pdf_bytes, max_pages=max_pages)
    result.model = generic.model
    result.all_models = generic.all_models

    # If catalog has tables, try to find row matching target power
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages[:max_pages]:
            tables = page.extract_tables()
            for table in tables:
                if not table:
                    continue
                for row in table:
                    if not row:
                        continue
                    row_text = " ".join(str(c) for c in row if c)
                    # Check if row contains target power
                    for cell in row:
                        if cell is None:
                            continue
                        try:
                            val = float(str(cell).replace(',', '.').strip())
                            if abs(val - target_power_kw) < 0.5:
                                # Found matching row - try to extract values
                                numbers = []
                                for c in row:
                                    if c is None:
                                        continue
                                    try:
                                        numbers.append(float(str(c).replace(',', '.').strip()))
                                    except ValueError:
                                        pass
                                # Try to map numbers to specs based on position and value ranges
                                for n in numbers:
                                    if 200 <= n <= 1500 and result.vdc_max is None:
                                        result.vdc_max = n
                                    elif 1 <= n <= 500 and n != target_power_kw:
                                        if result.output_current_nominal is None and n < 100:
                                            result.output_current_nominal = n
                                # Extract model name from row
                                for c in row:
                                    if c and re.search(r'[A-Z]{2,}.*\d', str(c)):
                                        result.model = str(c).strip()
                                        break
                        except ValueError:
                            continue

    # Fill in from generic extraction what wasn't found
    for attr in ['vdc_max', 'vdc_range_min', 'vdc_range_max', 'vdc_mpp',
                 'vdc_start', 'vdc_min_work', 'input_current_nominal',
                 'input_current_max', 'output_current_nominal']:
        if getattr(result, attr) is None:
            setattr(result, attr, getattr(generic, attr))

    result.power_kw = target_power_kw
    return result
