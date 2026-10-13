import fcntl
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
import recovery
import service


def healthy(stamp=None):
    stamp=time.time() if stamp is None else stamp
    return dict(installed=True,paused=False,fresh=True,pid=42,bridge=dict(updated_at=stamp,connection='connected',data_source='ok',device_supported=True,device_at=stamp,device_error=None,device={'firmware':'0.25'}))


class RecoveryTests(unittest.TestCase):
    def test_only_new_live_device_confirmation_counts_as_recovered(self):
        state=healthy(101)
        self.assertEqual(recovery.outcome(state,100,102),'synced')
        for patch_values in ({'device_at':99},{'device_at':103},{'device_at':60},{'device_error':'timeout'},{'device':None},{'connection':'waiting_ble'}):
            changed=healthy(101);changed['bridge'].update(patch_values)
            self.assertEqual(recovery.outcome(changed,100,102),'waiting_device')
        state['bridge']['data_source']='unavailable'
        self.assertEqual(recovery.outcome(state,100,102),'data_unavailable')
        state['bridge']['device_supported']=False
        self.assertEqual(recovery.outcome(state,100,102),'firmware_update_required')
        state['fresh']=False
        self.assertEqual(recovery.outcome(state,100,102),'service_unavailable')
        state['paused']=True
        self.assertEqual(recovery.outcome(state,100,102),'paused')

    def test_pause_requires_explicit_resume_and_preserves_configuration(self):
        with tempfile.TemporaryDirectory() as root:
            loc=service.Locations(root);config=dict(paused=True,transport='ble',ble_device='fixture',serial_number='fixture',codex_home='fixture')
            calls=[]
            def resume(_):calls.append('resume');config['paused']=False
            with patch.object(service,'owned',side_effect=lambda _:dict(config)), patch.object(service,'status',side_effect=lambda *a,**k:dict(healthy(),paused=config['paused'])), patch.object(service,'stop_loaded',side_effect=lambda _:calls.append('stop')), patch.object(service,'resume',side_effect=resume):
                result=recovery.recover(loc,timeout=0)
                self.assertEqual(result['outcome'],'paused');self.assertEqual(calls,[])
                result=recovery.recover(loc,allow_resume=True,timeout=0)
                self.assertTrue(result['ok']);self.assertEqual(calls,['stop','resume'])
                self.assertEqual(config,dict(paused=False,transport='ble',ble_device='fixture',serial_number='fixture',codex_home='fixture'))

    def test_reconnect_releases_old_owner_before_resume_and_does_not_claim_offline_success(self):
        with tempfile.TemporaryDirectory() as root:
            loc=service.Locations(root);calls=[];state=healthy();state['bridge']['connection']='waiting_ble'
            with patch.object(service,'owned',return_value={'paused':False}), patch.object(service,'status',return_value=state), patch.object(service,'stop_loaded',side_effect=lambda _:calls.append('stop')), patch.object(service,'resume',side_effect=lambda _:calls.append('resume')):
                result=recovery.recover(loc,timeout=0)
                self.assertFalse(result['ok']);self.assertEqual(result['outcome'],'waiting_device');self.assertEqual(calls,['stop','resume'])

    def test_stop_failure_and_concurrent_recovery_do_not_spawn_another_service(self):
        with tempfile.TemporaryDirectory() as root:
            loc=service.Locations(root)
            with patch.object(service,'owned',return_value={'paused':False}), patch.object(service,'stop_loaded',side_effect=RuntimeError('not stopped')), patch.object(service,'resume') as resume:
                self.assertEqual(recovery.recover(loc,timeout=0)['outcome'],'recovery_failed');resume.assert_not_called()
            with (loc.runtime/'recovery.lock').open('a+') as lock:
                fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
                with patch.object(service,'stop_loaded') as stop:
                    self.assertEqual(recovery.recover(loc,timeout=0)['outcome'],'busy');stop.assert_not_called()

    def test_new_pause_during_reconnect_is_respected(self):
        with tempfile.TemporaryDirectory() as root:
            loc=service.Locations(root)
            with patch.object(service,'owned',side_effect=[{'paused':False},{'paused':True}]), patch.object(service,'stop_loaded'), patch.object(service,'resume') as resume, patch.object(service,'status',return_value=dict(healthy(),paused=True)):
                self.assertEqual(recovery.recover(loc,timeout=0)['outcome'],'paused');resume.assert_not_called()


if __name__=='__main__':unittest.main()
