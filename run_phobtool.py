"""Lanceur : python run_phobtool.py (aussi utilisé comme point d'entrée PyInstaller)."""
import sys

from phobtool.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
