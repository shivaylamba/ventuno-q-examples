import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'ai-balance-challenge/python'))
from balance import BalanceGame, angle, knob_delta

class BalanceTests(unittest.TestCase):
    def setUp(self):self.g=BalanceGame();self.seq=0;self.now=0
    def feed(self,seconds,accel=(0,0,1),gyro=(0,0,0),age=0,repeat=False):
        for _ in range(round(seconds/.05)):
            self.now+=.05
            if not repeat:self.seq+=1
            self.g.tick(self.seq,age,accel,gyro,True,self.now)
    def active(self):
        self.feed(.05);self.g.start(self.now);self.feed(2.2)
        self.assertEqual(self.g.phase,'active')
    def test_calibration_and_five_second_win(self):
        self.active();self.feed(4.7);self.assertEqual(self.g.phase,'active')
        self.feed(.5);self.assertTrue(self.g.result['won'])
        self.assertEqual(self.g.result['score'],100)
    def test_motion_resets_hold(self):
        self.active();self.feed(2);self.feed(.4,gyro=(100,0,0))
        self.assertEqual(self.g.held,0);self.assertEqual(self.g.resets,1)
        self.feed(5.1);self.assertTrue(self.g.result['won']);self.assertLess(self.g.result['score'],100)
    def test_no_progress_from_repeated_packets(self):
        self.active();held=self.g.held;self.feed(10,repeat=True)
        self.assertEqual(self.g.held,held);self.assertEqual(self.g.phase,'active')
    def test_stale_sensor_cannot_win(self):
        self.active();self.feed(1);self.feed(.05,age=500)
        self.assertFalse(self.g.result['won']);self.assertFalse(self.g.sensor_ready)
    def test_cannot_start_without_sensor(self):
        with self.assertRaises(ValueError):self.g.start(0)
    def test_turn_wrap_and_reference_angle(self):
        self.assertEqual(knob_delta(-32768,32767),1)
        self.assertAlmostEqual(angle((0,0,1),(1,0,0)),90)
    def test_calibration_must_settle(self):
        self.feed(.05);self.g.start(self.now);self.feed(3,gyro=(80,0,0))
        self.assertEqual(self.g.phase,'calibrating');self.assertEqual(self.g.calibration_progress,0)

if __name__=='__main__':unittest.main()
