"""Offline tests only: no identity reads, microphone, playback or network calls."""
from pathlib import Path
import subprocess,sys
root=Path(__file__).resolve().parents[1]
subprocess.run([sys.executable,'checks/generate_voice_fixture.py'],cwd=root,check=True)
subprocess.run([sys.executable,'-m','unittest','discover','-s','checks','-p','test_*.py'],cwd=root,check=True)
