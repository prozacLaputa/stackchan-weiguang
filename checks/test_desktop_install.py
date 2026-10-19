"""安装边界使用临时目录与合成内容，不访问真实身份或修改系统安装。"""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parent.parent
spec=importlib.util.spec_from_file_location('desktop_installer',ROOT/'macos/install_desktop.py')
installer=importlib.util.module_from_spec(spec);spec.loader.exec_module(installer)


class DesktopInstallTests(unittest.TestCase):
    def test_runtime_imports_without_developer_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for relative in installer.RUNTIME_FILES:
                destination=root/relative;destination.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(ROOT/relative,destination)
            code="""import sys
sys.dont_write_bytecode=True
sys.path[:0]=[sys.argv[1]+'/bridge',sys.argv[1]+'/checks']
import factory_voice_client,vision_camera,control,presence,runtime
assert all(m.__file__.startswith(sys.argv[1]) for m in (factory_voice_client,vision_camera,control,presence,runtime))
"""
            subprocess.run([sys.executable,'-I','-c',code,str(root)],cwd=tmp,check=True,capture_output=True)

    def test_package_rejects_changed_or_extra_files(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(installer,'verify_bundle',return_value={}):
            root=Path(tmp);item=root/'program';item.write_bytes(b'original')
            (root/'manifest.json').write_text(json.dumps({'program':installer.digest(item)}))
            installer.verify_package(root)
            item.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'checksum'):installer.verify_package(root)
            item.write_bytes(b'original');(root/'private.key').write_bytes(b'fixture')
            with self.assertRaisesRegex(ValueError,'files_changed'):installer.verify_package(root)

    def test_symlink_and_arbitrary_destination_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            home=Path(tmp);destination=home/'Applications'/installer.NAME
            installer.validate_destination(destination,home)
            with self.assertRaises(ValueError):installer.validate_destination(home/'Documents'/installer.NAME,home)
            destination.parent.mkdir();destination.symlink_to(home/'other')
            with self.assertRaises(ValueError):installer.validate_destination(destination,home)

    def test_missing_or_mismatched_managed_backup_is_rejected(self):
        spec=importlib.util.spec_from_file_location('identity_fixture',ROOT/'checks/factory_voice_identity.py')
        identity=importlib.util.module_from_spec(spec);spec.loader.exec_module(identity)
        with tempfile.TemporaryDirectory() as tmp,patch.object(identity,'ROOT',Path(tmp)):
            root=Path(tmp);(root/'backups').mkdir()
            with self.assertRaises(FileNotFoundError):identity.read_identity()
            (root/'backups/factory.bin').write_bytes(b'fixture')
            for checksum in ('','0'*64,'invalid'):
                (root/'backups/factory.sha256').write_text(checksum)
                with self.assertRaisesRegex(ValueError,'checksum_mismatch'):identity.read_identity()

if __name__=='__main__':unittest.main()
