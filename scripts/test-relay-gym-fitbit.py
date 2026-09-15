#!/usr/bin/env python3
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('relay', Path(__file__).with_name('relay-gym-fitbit.py'))
relay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(relay)


class SelectionTests(unittest.TestCase):
    def state(self, observed, status='live'):
        return {'status': status, 'observedAtMs': observed, 'updatedAtMs': observed, 'bpm': 90}

    def test_fresh_gym_remains_live(self):
        selected = relay.mark_freshness(self.state(98000), 100000)
        self.assertEqual(selected['receiver'], 'gym-pi')
        self.assertEqual(selected['status'], 'live')

    def test_no_reading_is_not_live(self):
        self.assertEqual(relay.mark_freshness(self.state(None), 100000)['status'], 'scanning')

    def test_connecting_gym_remains_connecting(self):
        selected = relay.mark_freshness(self.state(99000, 'connecting'), 100000)
        self.assertEqual(selected['status'], 'connecting')

    def test_dead_process_is_not_fresh_even_with_recent_reading(self):
        state = self.state(99000)
        state['updatedAtMs'] = 50000
        self.assertEqual(relay.mark_freshness(state, 100000)['status'], 'scanning')

    def test_stale_values_remain_explicit_without_changing_capture_time(self):
        original = self.state(80000)
        selected = relay.mark_freshness(original, 100000)
        self.assertEqual(selected['status'], 'scanning')
        self.assertEqual(selected['observedAtMs'], 80000)
        self.assertEqual(original['status'], 'live')


if __name__ == '__main__':
    unittest.main()
