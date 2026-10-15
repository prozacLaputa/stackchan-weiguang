import sys
from pathlib import Path
import unittest
import base64
import collections
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'bridge'))
from vision_camera import Interaction,Camera,display_feedback

def observation(x=.5,hand=None):
    value={'ok':True,'faces':1,'face':[x,.5]}
    if hand is not None:value['hand']=[hand,.6]
    return value

class Tests(unittest.TestCase):
    def test_feedback_uses_robot_state_not_only_face_detection(self):
        self.assertIn('当前表情',display_feedback(b'VISUAL_OK\tanimation'))
        self.assertIn('微笑',display_feedback(b'VISUAL_OK\tsmiling'))
        self.assertIn('主屏',display_feedback(b'VISUAL_OK\tpage'))
        self.assertNotIn('跟随中',display_feedback(b'VISUAL_OK'))

    def camera(self,parts):
        class Link:
            in_waiting=1
            def __init__(self):self.parts=collections.deque(parts)
            def read(self,_):return self.parts.popleft() if self.parts else b''
            def write(self,_):pass
        camera=Camera.__new__(Camera);camera.link=Link();camera.buffer=bytearray();camera.seq=0
        return camera

    def test_split_serial_lines_keep_partial_bytes(self):
        c=self.camera([b'CAM_D',b'',b'ATA\t1\t0\tYWJj',b'\nPOWER\t80\t1\n'])
        self.assertEqual(c.readline(time.monotonic()+1),b'CAM_DATA\t1\t0\tYWJj')
        self.assertEqual(c.readline(time.monotonic()+1),b'POWER\t80\t1')

    def test_frame_interleaves_diagnostics_and_rejects_duplicate_offset(self):
        jpeg=b'\xff\xd8'+b'x'*500+b'\xff\xd9'
        header=b'CAM_FRAME\t1\t504\n'
        first=b'CAM_DATA\t1\t0\t'+base64.b64encode(jpeg[:384])+b'\n'
        last=b'CAM_DATA\t1\t384\t'+base64.b64encode(jpeg[384:])+b'\n'
        c=self.camera([header[:10],header[10:]+first[:100],first[100:],b'MOTION\tend\n',last])
        self.assertEqual(c.frame(),jpeg)
        c=self.camera([header,first,first])
        with self.assertRaisesRegex(RuntimeError,'frame_chunk'):c.frame()

    def test_presence_and_occlusion(self):
        a=Interaction()
        self.assertIsNone(a.update(observation(),0)[0]);self.assertIsNone(a.update(observation(),.4)[0])
        self.assertEqual(a.update(observation(),.8)[0][2],1)
        a.update({'faces':0},1)
        for t in (1.4,1.8):self.assertIsNone(a.update(observation(),t)[0])
        self.assertEqual(a.update(observation(),2.2)[0][2],0)
        for t in (35,35.4):a.update(observation(),t)
        self.assertEqual(a.update(observation(),35.8)[0][2],1)

    def test_stationary_palm_and_wave_cooldown(self):
        a=Interaction()
        for i in range(10):
            pose,_=a.update(observation(hand=.4),i*.35)
            if pose:self.assertNotEqual(pose[2],2)
        events=[a.update(observation(hand=x),4+i*.35)[0][2] for i,x in enumerate((.3,.4,.55,.4,.3))]
        self.assertEqual(events.count(2),1)
        for i,x in enumerate((.3,.5,.3,.5,.3)):
            self.assertNotEqual(a.update(observation(hand=x),6+i*.35)[0][2],2)

    def test_multiple_and_invalid_faces_never_follow(self):
        a=Interaction()
        for obs in ({'faces':2,'face':[.5,.5]}, {'faces':1,'face':[float('nan'),0]}, {'faces':1,'face':[1.1,0]}):
            self.assertIsNone(a.update(obs,1)[0])

if __name__=='__main__':unittest.main()
