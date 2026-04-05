#!/usr/bin/env python3
"""
Import personal content into Elysia/Guardian memory storage.
- Creates folder structure on thumb drive (F:\\ProjectGuardian\\memory\\personal\\...)
- Optionally OCRs ChatGPT screenshot PNGs from Downloads and saves as .txt in chatlogs
- For ChatGPT export .zip: use scripts/import_chatgpt_export.py path/to/export.zip

Run from project root: python scripts/import_personal_memory.py
Optional: python scripts/import_personal_memory.py --ocr   (requires pytesseract + Tesseract installed)
"""

import os
import sys
import argparse
from pathlib import Path

# Project root = parent of scripts/
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
MEMORY_BASE = Path("F:/ProjectGuardian/memory")
PERSONAL = MEMORY_BASE / "personal"
CHATLOGS = PERSONAL / "chatlogs"
JOURNAL = PERSONAL / "journal"
REFERENCE = PERSONAL / "reference"
DOWNLOADS = Path(os.path.expanduser("~")) / "Downloads"


def ensure_folders():
    """Create personal memory folders on thumb drive."""
    for folder in (PERSONAL, CHATLOGS, JOURNAL, REFERENCE):
        folder.mkdir(parents=True, exist_ok=True)
        print(f"  [OK] {folder}")
    readme = PERSONAL / "README.txt"
    if not readme.exists():
        readme.write_text(
            "Add your text/markdown files here. Elysia will use them for memory.\n"
            " - chatlogs/  : ChatGPT exports, conversation logs\n"
            " - journal/   : Notes, diaries\n"
            " - reference/ : Articles, research\n",
            encoding="utf-8",
        )
        print(f"  [OK] Created {readme}")
    return True


def find_chatgpt_screenshots():
    """Find ChatGPT Image *.png in Downloads."""
    if not DOWNLOADS.exists():
        return []
    out = []
    for f in DOWNLOADS.iterdir():
        if f.is_file() and f.suffix.lower() == ".png" and "ChatGPT" in f.name:
            out.append(f)
    return sorted(out, key=lambda p: p.stat().st_mtime, reverse=True)


def ocr_image(path: Path) -> str:
    """Extract text from image using pytesseract if available."""
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        return ""
    try:
        img = Image.open(path)
        return pytesseract.image_to_string(img) or ""
    except Exception:
        return ""


def run_ocr(screenshots: list, out_dir: Path, dry_run: bool = False):
    """OCR each screenshot and save as .txt in out_dir."""
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        print("  [SKIP] OCR requires: pip install pytesseract Pillow")
        print("        and Tesseract installed on the system (https://github.com/tesseract-ocr/tesseract)")
        return 0
    count = 0
    for path in screenshots:
        name = path.stem + ".txt"
        out_path = out_dir / name
        if dry_run:
            print(f"  Would create {out_path.name}")
            count += 1
            continue
        text = ocr_image(path)
        if not text.strip():
            continue
        out_path.write_text(text, encoding="utf-8")
        print(f"  [OK] {out_path.name}")
        count += 1
    return count


def main():
    parser = argparse.ArgumentParser(description="Set up personal memory folders and optionally import ChatGPT screenshots")
    parser.add_argument("--ocr", action="store_true", help="OCR ChatGPT screenshot PNGs from Downloads into chatlogs")
    parser.add_argument("--dry-run", action="store_true", help="Only list what would be done")
    args = parser.parse_args()

    print("Elysia personal memory import")
    print("-----------------------------")

    # 1. Ensure folder structure
    print("\n1. Creating folders on F:\\ProjectGuardian\\memory\\personal\\...")
    if not args.dry_run:
        ensure_folders()
    else:
        for folder in (PERSONAL, CHATLOGS, JOURNAL, REFERENCE):
            print(f"  Would ensure {folder}")

    # 2. Optional OCR of ChatGPT screenshots
    screenshots = find_chatgpt_screenshots()
    print(f"\n2. Found {len(screenshots)} ChatGPT screenshot(s) in Downloads.")
    if args.ocr and screenshots:
        print("   Running OCR and saving .txt to personal/chatlogs/ ...")
        n = run_ocr(screenshots, CHATLOGS, dry_run=args.dry_run)
        print(f"   Created {n} text file(s).")
    elif args.ocr and not screenshots:
        print("   No ChatGPT PNGs found in Downloads.")
    else:
        print("   Run with --ocr to extract text from screenshots (requires pytesseract + Pillow).")

    print("\nDone. Add more .txt/.md files to F:\\ProjectGuardian\\memory\\personal\\ as needed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
