import hashlib, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
import factory_voice_identity as identity

class ChecksumTests(unittest.TestCase):
    def test_uses_owners_checksum_and_fails_before_parsing_wrong_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'backups').mkdir()
            (root/'backups/factory.bin').write_bytes(b'fixture')
            checksum=root/'backups/factory.sha256'
            with patch.object(identity,'ROOT',root):
                for text in ('','not-a-checksum','0'*64):
                    checksum.write_text(text)
                    with self.assertRaisesRegex(ValueError,'factory_backup_checksum_mismatch'):identity.read_identity()
                checksum.write_text(hashlib.sha256(b'fixture').hexdigest()+'  factory.bin')
                with self.assertRaisesRegex(ValueError,'nvs_not_found'):identity.read_identity()
