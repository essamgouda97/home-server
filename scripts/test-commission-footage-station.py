#!/usr/bin/env python3
"""Power acceptance uses actual firmware bit meanings, not a generic nonzero test."""
import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('commission',Path(__file__).with_name('commission-footage-station.py'))
commission=importlib.util.module_from_spec(spec);spec.loader.exec_module(commission)

class PowerTests(unittest.TestCase):
    def test_current_and_earlier_undervoltage_block_importer_install(self):
        for flags in ('0x1','0x50005','0x10000','0x50000'):
            with self.subTest(flags=flags),self.assertRaisesRegex(ValueError,'undervoltage'):
                commission.require_stable_power(('throttled='+flags+'\n').encode())

    def test_unrelated_firmware_flags_are_not_misclassified_as_undervoltage(self):
        for flags in ('0x0','0x80000','0x20000'):
            commission.require_stable_power(('throttled='+flags+'\n').encode())
        for response in (b'',b'permission denied',b'throttled=0x0\nother output'):
            with self.assertRaises(ValueError):commission.require_stable_power(response)

if __name__=='__main__':unittest.main()
