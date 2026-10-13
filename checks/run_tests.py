"""Run local tests without a real robot or the user's task database."""
from pathlib import Path
import subprocess
import sys
root=Path(__file__).resolve().parents[1]
subprocess.run([sys.executable,'-m','unittest','discover','-s','bridge','-p','test_*.py'],cwd=root,check=True)
dependency=root/'.pio/libdeps/stackchan/M5Unified/src/utility/Touch_Class.inl'
if not dependency.is_file():
    raise SystemExit('Run .venv/bin/pio run first; the touch pipeline test uses the pinned M5Unified implementation.')
out=root/'.runtime/tests';out.mkdir(parents=True,exist_ok=True)
for source in sorted((root/'tests').glob('*_test.cpp')):
    target=out/source.stem
    subprocess.run(['clang++','-std=c++11','-fsanitize=address,undefined','-fno-omit-frame-pointer','-Isrc','-Itests/support','-Itests/support/motion',str(source),'-o',str(target)],cwd=root,check=True)
    subprocess.run([str(target)],cwd=root,check=True)
    print(source.name+' passed',flush=True)
