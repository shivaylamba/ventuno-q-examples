import unittest
import math
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
from control import Gearbox, hand_signal, steering, wrist_roll, WristThrottle
class Controls(unittest.TestCase):
    def test_mirrored_handlebars_direction(self):
        signal, mode, valid=hand_signal([{'x':.8,'y':.3,'confidence':.9},{'x':.2,'y':.6,'confidence':.9}])
        self.assertTrue(valid);self.assertEqual(mode,'handlebars');self.assertLess(steering(signal,mode,0),0)
    def test_low_confidence_and_nan(self):
        self.assertFalse(hand_signal([{'x':float('nan'),'y':0,'confidence':1},{'x':.5,'y':.5,'confidence':.1}])[2])
    def test_calibration_and_deadzone(self):
        self.assertEqual(steering(.2,'handlebars',.2),0);self.assertEqual(steering(2,'handlebars',0),-1)
    def test_single_hand_physical_direction(self):
        signal, mode, valid = hand_signal([{'x':.8,'y':.5,'confidence':.9}])
        self.assertTrue(valid);self.assertGreater(steering(signal,mode,0),0)
    def test_relative_shift_bounds_and_wrap(self):
        g=Gearbox();g.update(32767,0);g.update(-32768,0);self.assertEqual(g.gear,2)
        g.update(-32760,1);self.assertEqual(g.gear,6);g.disconnect();g.update(100,1);self.assertEqual(g.gear,6)
    def test_encoder_reset_ignored(self):
        g=Gearbox();g.update(200,0);g.update(0,0);self.assertEqual(g.gear,1)

def palm(depth=0, x=.8, label='right'):
    points=[[x,.5,0] for _ in range(21)]
    points[5]=[x+.025,.45,depth];points[17]=[x-.025,.45,0]
    return {'x':x,'y':.5,'confidence':.95,'handedness':label,'landmarks':points}

class Throttle(unittest.TestCase):
    def test_opposite_twist_brakes_instead_of_accelerating(self):
        t=WristThrottle()
        for now in [0,.1,.2]:t.update([palm()],now)
        t.auto_calibrate(.2)
        for i in range(12):t.update([palm(20)],.3+i*.1)
        self.assertGreater(t.value,.9);self.assertEqual(t.brake,0)
        for i in range(12):t.update([palm(-20)],2+i*.1)
        self.assertEqual(t.value,0);self.assertGreater(t.brake,.9)
        for i in range(20):t.update([palm()],4+i*.1)
        self.assertLess(t.brake,.01);self.assertLess(t.value,.01)
    def test_first_negative_twist_can_define_acceleration(self):
        t=WristThrottle()
        for now in [0,.1,.2]:t.update([palm()],now)
        t.auto_calibrate(.2)
        for i in range(12):t.update([palm(-20)],.3+i*.1)
        self.assertGreater(t.value,.9);self.assertEqual(t.direction,-1)
        for i in range(12):t.update([palm(20)],2+i*.1)
        self.assertEqual(t.value,0);self.assertGreater(t.brake,.9)
    def test_automatic_start_without_hand_waits_for_real_reference(self):
        t=WristThrottle();t.auto_calibrate(0)
        self.assertFalse(t.ready)
        for now in [1,1.1,1.2]:t.update([palm(10)],now)
        self.assertTrue(t.ready);self.assertAlmostEqual(t.value,0)
        for i in range(10):t.update([palm(20)],1.3+i*.1)
        self.assertGreater(t.value,.5)
    def test_auto_tracking_survives_handedness_label_flip(self):
        t=WristThrottle()
        for now in [0,.1,.2]:t.update([palm()],now)
        t.auto_calibrate(.2);t.update([palm(20,label='left')],.3)
        self.assertTrue(t.valid)
    def test_translation_and_steering_do_not_change_roll(self):
        a=palm(12);b=palm(12,.4)
        self.assertAlmostEqual(wrist_roll(a),wrist_roll(b))
        for index in [5,17]:
            p=b['landmarks'][index];xx=(p[0]-.4)*640;yy=(p[1]-.45)*480
            p[0]=.4+(xx*math.cos(.5)-yy*math.sin(.5))/640
            p[1]=.45+(xx*math.sin(.5)+yy*math.cos(.5))/480
        self.assertAlmostEqual(wrist_roll(a),wrist_roll(b))
    def test_two_pose_calibration_and_release(self):
        t=WristThrottle()
        for now in [0,.1,.2]:t.update([palm()],now)
        t.calibrate('rest',.2)
        for now in [.3,.4,.5]:t.update([palm(20)],now)
        t.calibrate('full',.5)
        for i in range(20):t.update([palm(20)],.6+i*.1)
        self.assertTrue(t.ready);self.assertGreater(t.value,.99)
        for i in range(20):t.update([palm()],3+i*.1)
        self.assertLess(t.value,.01)
        t.update([palm(20,.2,'left')],5);self.assertFalse(t.valid);self.assertEqual(t.value,0)
    def test_missing_landmarks_and_insufficient_twist(self):
        self.assertIsNone(wrist_roll({'confidence':1,'x':.5,'landmarks':[]}))
        t=WristThrottle()
        for now in [0,.1,.2]:t.update([palm()],now)
        t.calibrate('rest',.2)
        for now in [.3,.4,.5]:t.update([palm()],now)
        with self.assertRaises(ValueError):t.calibrate('full',.5)
        self.assertFalse(t.ready)
    def test_reverse_twist_calibration_is_supported(self):
        t=WristThrottle()
        for now in [0,.1,.2]:t.update([palm(20)],now)
        t.calibrate('rest',.2)
        for now in [.3,.4,.5]:t.update([palm()],now)
        t.calibrate('full',.5)
        for i in range(20):t.update([palm()],.6+i*.1)
        self.assertGreater(t.value,.99)

class DepthUnits(unittest.TestCase):
    def test_inverse_roi_scale_including_rotation(self):
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
        from perception.landmark_units import camera_depth_scale
        self.assertAlmostEqual(camera_depth_scale([[.5,0,42],[0,.5,21]]),.5)
        self.assertAlmostEqual(camera_depth_scale([[0,-.5,42],[.5,0,21]]),.5)
if __name__=='__main__':unittest.main()
