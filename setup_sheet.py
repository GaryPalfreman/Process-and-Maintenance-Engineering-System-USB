import io
import json
import re
from datetime import datetime
from typing import Dict, List, Optional

from fpdf import FPDF

SETUP_FIELDS = [
    "Work Holding",
    "Jaws/Fixture Name",
    "Jaw/Work Holding Location",
    "Drawing No + Revision",
    "Machine",
    "Program Name",
    "Setup Time",
    "Cycle Time",
    "Actual Time",
    "Comments",
]

TOOL_FIELDS = [
    "Tool No + Offset No",
    "Tool Type",
    "GE REF No",
    "Wear Offset X",
    "Wear Offset Z",
    "Change Frequency",
]


def blank_setup() -> Dict[str, str]:
    return {field: "" for field in SETUP_FIELDS}


def blank_tool() -> Dict[str, str]:
    return {field: "" for field in TOOL_FIELDS}


def sanitize_filename(text: str) -> str:
    text = (text or "setup_sheet").strip()
    text = re.sub(r"[^A-Za-z0-9._-]+", "_", text)
    return text.strip("._-") or "setup_sheet"


def build_filename_prefix(inputs: Dict[str, str]) -> str:
    drawing = sanitize_filename(inputs.get("Drawing No + Revision", "drawing"))
    program = sanitize_filename(inputs.get("Program Name", "program"))
    return f"Set_Up_Sheet_{drawing}_{program}"


def export_json(inputs: Dict[str, str], tools: List[Dict[str, str]]) -> bytes:
    data = {"user_inputs": inputs, "tool_inputs": tools}
    return json.dumps(data, indent=4, ensure_ascii=False).encode("utf-8")


def load_json_bytes(data: bytes):
    parsed = json.loads(data.decode("utf-8-sig"))
    if not isinstance(parsed, dict):
        raise ValueError("Setup sheet JSON must contain an object.")
    inputs = parsed.get("user_inputs", {})
    tools = parsed.get("tool_inputs", [])
    if not isinstance(inputs, dict) or not isinstance(tools, list):
        raise ValueError("Invalid setup sheet JSON structure.")
    normalized_inputs = blank_setup()
    normalized_inputs.update({k: str(v) for k, v in inputs.items() if k in normalized_inputs})
    normalized_tools = []
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        row = blank_tool()
        row.update({k: str(v) for k, v in tool.items() if k in row})
        normalized_tools.append(row)
    return normalized_inputs, normalized_tools


class SetupSheetPDF(FPDF):
    def __init__(self, logo_bytes: Optional[bytes] = None, created_by: str = "Gary Palfreman"):
        super().__init__(orientation="P", unit="mm", format="A4")
        self.logo_bytes = logo_bytes
        self.created_by = created_by

    def _draw_logo(self, x: float, y: float, w: float = 40):
        if not self.logo_bytes:
            return
        stream = io.BytesIO(self.logo_bytes)
        stream.name = "logo.png"
        try:
            self.image(stream, x=x, y=y, w=w)
        except Exception:
            pass

    def footer(self):
        self.set_y(-20)
        self.set_font("helvetica", size=8)
        current_date = datetime.now().strftime("%Y-%m-%d")
        self.cell(0, 8, f"Created by {self.created_by} on {current_date}", align="C")
        self._draw_logo(10, 270, 32)
        self._draw_logo(168, 270, 32)


def _fit_text(text: str, max_chars: int = 36) -> str:
    text = str(text or "")
    return text if len(text) <= max_chars else text[: max_chars - 1] + "…"


def generate_pdf_bytes(inputs: Dict[str, str], tool_data: List[Dict[str, str]], logo_bytes: Optional[bytes] = None, created_by: str = "Gary Palfreman") -> bytes:
    pdf = SetupSheetPDF(logo_bytes=logo_bytes, created_by=created_by)
    pdf.set_auto_page_break(auto=True, margin=25)
    pdf.add_page()
    pdf._draw_logo(10, 10, 40)
    pdf._draw_logo(160, 10, 40)
    pdf.set_font("helvetica", "B", 16)
    pdf.set_xy(55, 15)
    pdf.cell(100, 8, "Setup Sheet", align="C")
    pdf.set_font("helvetica", size=10)
    pdf.set_xy(55, 26); pdf.cell(100, 6, f"Machine: {inputs.get('Machine', '')}", align="C")
    pdf.set_xy(55, 33); pdf.cell(100, 6, f"Program Name: {inputs.get('Program Name', '')}", align="C")
    pdf.set_xy(55, 40); pdf.cell(100, 6, f"Drawing No + Revision: {inputs.get('Drawing No + Revision', '')}", align="C")
    pdf.ln(18)
    pdf.set_font("helvetica", size=10)
    for label in ["Work Holding", "Jaws/Fixture Name", "Jaw/Work Holding Location"]:
        pdf.cell(0, 8, f"{label}: {inputs.get(label, '')}", border=1, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    width = 190 / 3
    for label in ["Setup Time", "Cycle Time", "Actual Time"]:
        pdf.cell(width, 8, f"{label}: {inputs.get(label, '')}", border=1, align="C")
    pdf.ln(10)
    pdf.multi_cell(0, 8, f"Comments: {inputs.get('Comments', '')}", border=1)
    pdf.ln(5)
    pdf.set_font("helvetica", "B", 10)
    pdf.cell(0, 8, "Tool Data", new_x="LMARGIN", new_y="NEXT")
    headers = ["Tool Type", "GE REF No", "Tool No + Offset No", "Wear Offset X", "Wear Offset Z", "Change Frequency"]
    widths = [38, 25, 39, 27, 27, 34]
    for header, w in zip(headers, widths):
        pdf.cell(w, 8, header, border=1, align="C")
    pdf.ln()
    pdf.set_font("helvetica", size=8)
    for tool in tool_data:
        if pdf.get_y() > 255:
            pdf.add_page()
            pdf.set_font("helvetica", "B", 10)
            for header, w in zip(headers, widths):
                pdf.cell(w, 8, header, border=1, align="C")
            pdf.ln(); pdf.set_font("helvetica", size=8)
        values = [tool.get("Tool Type", ""), tool.get("GE REF No", ""), tool.get("Tool No + Offset No", ""), tool.get("Wear Offset X", ""), tool.get("Wear Offset Z", ""), tool.get("Change Frequency", "")]
        for value, w in zip(values, widths):
            pdf.cell(w, 8, _fit_text(value), border=1, align="C")
        pdf.ln()
    return bytes(pdf.output())
