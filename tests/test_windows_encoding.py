import unittest
from pathlib import Path
from unittest.mock import patch
from audit_desk.core import Desk

class WindowsEncodingRegression(unittest.TestCase):
    def test_cpu_startup_in_non_utf8_text_locale(self):
        original=Path.read_text
        def legacy_locale(path,*args,**kwargs):
            kwargs.setdefault('encoding','cp949')
            return original(path,*args,**kwargs)
        with patch.object(Path,'read_text',legacy_locale):
            desk=Desk()
        self.assertTrue(desk.policies)
        self.assertTrue(desk.evidence)

if __name__=='__main__':unittest.main()
