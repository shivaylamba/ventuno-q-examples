"""Unit conversion for hand ROI depth exported to the full-camera tracker."""
import math

def camera_depth_scale(inverse_affine):
    a, b = inverse_affine[0][:2]
    c, d = inverse_affine[1][:2]
    return math.sqrt(abs(float(a)*float(d)-float(b)*float(c)))
