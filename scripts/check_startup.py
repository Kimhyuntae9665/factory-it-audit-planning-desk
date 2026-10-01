"""CPU startup and frozen-source integrity smoke check; no model calls."""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from audit_desk.core import Desk
Desk()
print("CPU startup and source integrity passed")
