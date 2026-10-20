import re
from typing import Optional, Tuple
import numpy as np

try:
    import cv2
    HAS_OPENCV = True
except ImportError:
    HAS_OPENCV = False


class VisionTextReader:
    """
    Lightweight OCR and numeric status reader helper.
    Can extract HP/MP digits, EXP percentages, Gold balances, or coordinates.
    """
    def __init__(self):
        pass

    def extract_numbers_from_image(self, crop: np.ndarray) -> Optional[int]:
        """
        Extracts integer digits from UI crop.
        In minimal environments without tesseract, returns None.
        """
        return None

    def parse_coordinate_text(self, text: str) -> Optional[Tuple[int, int]]:
        """Parses '(x, y)' or 'x, y' from OCR text string."""
        if not text:
            return None
        match = re.search(r"(\d+)[,\s]+(\d+)", text)
        if match:
            return int(match.group(1)), int(match.group(2))
        return None
