"""Generate a one-second local tone for offline codec tests; never plays audio."""
from pathlib import Path
import shutil, subprocess
root=Path(__file__).resolve().parents[1]
target=root/'.runtime/fixtures/synthetic-input.ogg'
target.parent.mkdir(parents=True,exist_ok=True)
ffmpeg=shutil.which('ffmpeg')
if not ffmpeg:raise SystemExit('Install ffmpeg to run optional voice tests.')
subprocess.run([ffmpeg,'-hide_banner','-loglevel','error','-y','-f','lavfi','-i',
               'sine=frequency=440:sample_rate=16000:duration=1','-ac','1',
               '-c:a','libopus','-frame_duration','60',str(target)],check=True)
print('Generated synthetic fixture; no audio output or network.')
