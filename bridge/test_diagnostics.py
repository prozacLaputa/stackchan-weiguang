import json
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

from diagnostics import Journal, LIMIT, clean_snapshot, export_bundle, read_events
from runtime import Bridge, atomic_json
from test_runtime import FakeSerial, port, task
import service


def snapshot(**device_changes):
    device={'firmware':'0.30','uptime':100,'motion_state':'ready','motion_reason':'none',
            'pet_event':0,'pet_result':'none','pet_reason':'none','pet':1,'wait_motion':0,'done_motion':0}
    device.update(device_changes)
    return {'connection':'connected','transport':'ble','data_source':'ok','device':device,
            'device_at':time.time(),'tasks':8,'running':1,'needs_input':0,'error':None,'device_error':None}


class DiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.loc=service.Locations(self.temp.name);self.loc.runtime.mkdir(parents=True)
        self.journal=Journal(self.loc.runtime)

    def kinds(self):return [r['kind'] for r in read_events(self.loc.runtime)[0]]

    def test_fault_survives_service_restart_and_device_recovery_is_recorded(self):
        self.journal.observe(snapshot())
        fault=snapshot(motion_state='unavailable',motion_reason='load-high',pet_event=1,pet_result='failed',pet_reason='load-high')
        self.journal.observe(fault)
        for _ in range(20):self.journal.observe(fault)
        self.assertEqual(self.kinds().count('motion_issue'),1)
        other=Journal(self.loc.runtime);other.observe(fault)
        self.assertEqual(self.kinds().count('motion_issue'),1)
        other.observe(snapshot(uptime=2))
        self.assertEqual(self.kinds().count('motion_recovered'),1)
        records=read_events(self.loc.runtime)[0]
        self.assertIn('load-high',json.dumps(records))

    def test_normal_petting_cooldown_and_screen_do_not_fill_journal(self):
        self.journal.observe(snapshot());before=len(self.kinds())
        for i in range(20):
            for result,reason,motion in [('moving','none','moving'),('completed','none','cooldown'),
                                         ('skipped','cooldown','cooldown'),('stopped','screen-touch','screen'),
                                         ('skipped','preference','disabled'),('skipped','too-short','ready')]:
                self.journal.observe(snapshot(pet_event=i,pet_result=result,pet_reason=reason,motion_state=motion))
        self.assertEqual(len(self.kinds()),before)

    def test_link_data_and_device_failures_get_one_transition_and_one_recovery(self):
        self.journal.observe(snapshot())
        bad=snapshot();bad.update(connection='waiting_ble',data_source='unavailable',device_error='confirmation_timeout')
        for _ in range(10):self.journal.observe(bad)
        self.journal.observe(snapshot())
        for kind in ('link_waiting','link_recovered','data_unavailable','data_recovered','device_issue','device_recovered'):
            self.assertEqual(self.kinds().count(kind),1,kind)
        old=snapshot();old['device_at']=time.time()-60;old['device']['motion_state']='unavailable'
        self.journal.observe(old);self.assertNotIn('motion_issue',self.kinds())

    def test_old_firmware_does_not_claim_fault_recovered(self):
        self.journal.observe(snapshot(motion_state='unavailable',motion_reason='load-high'))
        old=snapshot();old['device']={'firmware':'0.25'};self.journal.observe(old)
        self.assertNotIn('motion_recovered',self.kinds())

    def test_rotation_is_bounded_and_permissions_private(self):
        journal=Journal(self.loc.runtime,limit=2048)
        for i in range(120):
            journal.observe(snapshot(motion_state='unavailable' if i%2 else 'ready',motion_reason='load-high' if i%2 else 'none'))
        files=list(self.loc.runtime.glob('diagnostics.jsonl*'))
        self.assertEqual(len(files),3)
        self.assertTrue(all(p.stat().st_size<=2048 and p.stat().st_mode&0o777==0o600 for p in files))
        self.assertTrue(read_events(self.loc.runtime)[0])

    def test_export_contains_only_whitelisted_fields_even_with_injected_private_values(self):
        secret='DO_NOT_EXPORT_私密正文_and_key'
        raw=snapshot();raw.update(pending_tasks=[{'title':secret,'id':secret,'reason':secret}],port=secret,error=secret)
        raw['completion_events']=[{'title':secret,'id':secret,'key':secret,'completed_at':time.time()}]
        raw['desk_extras']={'music':{'title':secret,'artist':secret},'recap':{'rows':[{'id':secret,'title':secret}]}}
        raw['device'].update(firmware=secret,pet_reason=secret,chat=secret)
        raw['unknown']=secret
        self.journal.observe(raw)
        # 自由文本、原始日志和配置文件绝不原样带出。
        (self.loc.runtime/'bridge.log').write_text(secret)
        (self.loc.runtime/'startup-error.log').write_text(secret)
        (self.loc.root/'ble.key').write_text(secret)
        self.loc.config.write_text(secret)
        with (self.loc.runtime/'diagnostics.jsonl').open('a') as f:
            f.write(json.dumps({'at':time.time(),'kind':'motion_issue','private':secret,'snapshot':raw})+'\n')
            f.write(secret+'\n')
        atomic_json(self.loc.runtime/'status.json',raw)
        result=export_bundle(self.loc,{'installed':True,'loaded':False,'fresh':False,'paused':True})
        path=Path(result['path']);self.assertEqual(path.parent,self.loc.root/'diagnostics')
        self.assertEqual(path.stat().st_mode&0o777,0o600)
        with zipfile.ZipFile(path) as z:
            self.assertEqual(set(z.namelist()),{'report.json','events.jsonl','说明.txt','SHA256SUMS.json'})
            content=b'\n'.join(z.read(n) for n in z.namelist()).decode()
            self.assertNotIn(secret,content);self.assertNotIn(self.temp.name,content)
            report=json.loads(z.read('report.json'))
            self.assertFalse(report['last_snapshot']['device_live'])
            self.assertEqual(report['last_snapshot']['error'],'unknown')
            self.assertGreater(report['ignored_records'],0)
        self.assertTrue((self.loc.runtime/'bridge.log').read_text()==secret)

    def test_corrupt_and_linked_inputs_are_skipped_not_exported(self):
        private=Path(self.temp.name)/'private.txt';private.write_text('private marker')
        (self.loc.runtime/'diagnostics.jsonl').symlink_to(private)
        records,ignored=read_events(self.loc.runtime)
        self.assertFalse(records);self.assertEqual(ignored,1)
        with self.assertRaises(OSError):self.journal.observe(snapshot())
        self.assertEqual(private.read_text(),'private marker')
        corrupt=self.loc.runtime/'diagnostic-state.json';corrupt.write_text('{"connection": {"bad": "value"}}')
        (self.loc.runtime/'diagnostics.jsonl').unlink();self.journal.observe(snapshot())
        self.assertTrue(self.kinds())

    def test_diagnostic_disk_failure_does_not_stop_actual_bridge(self):
        link=FakeSerial()
        bridge=Bridge(SimpleNamespace(snapshot=lambda:[task()]),self.loc.runtime,
                      serial_factory=lambda:link,port_provider=lambda:[port()])
        with patch.object(bridge.diagnostics,'observe',side_effect=OSError('disk full')):
            bridge.step()
        self.assertIs(bridge.link,link)
        status=json.loads((self.loc.runtime/'status.json').read_text())
        self.assertFalse(status['diagnostics_ok']);self.assertEqual(status['connection'],'connected')

    def test_actual_bridge_records_disconnect_without_titles_or_ids(self):
        link=FakeSerial();bridge=Bridge(SimpleNamespace(snapshot=lambda:[task()]),self.loc.runtime,
                                      serial_factory=lambda:link,port_provider=lambda:[port()])
        bridge.step();link.fail=True;bridge.last_sent_at-=6;bridge.step()
        self.assertIn('link_waiting',self.kinds())
        self.assertNotIn('私密任务标题',json.dumps(read_events(self.loc.runtime)[0],ensure_ascii=False))

    def test_nonfinite_bad_types_and_long_reason_are_removed(self):
        raw=snapshot();raw.update(ack_ms=float('nan'),tasks={'private':1},error=['secret'])
        raw['device']['motion_reason']='x'*99999
        clean=clean_snapshot(raw)
        self.assertNotIn('ack_ms',clean);self.assertNotIn('tasks',clean)
        self.assertEqual(clean['device']['motion_reason'],'unknown')
