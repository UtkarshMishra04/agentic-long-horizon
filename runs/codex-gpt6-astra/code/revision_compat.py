"""Prove that staged records exercise unchanged non-under-rack code paths.

Original source hashes are retained. Under-rack episodes must use the final
revision. Archived snapshots and the exact scoped replacement prove equivalence
for the seven other tasks; there is no blanket acceptance of older results.
"""
import hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parent
SNAPSHOTS={
 'dbb5db611c54392793db9214c5a0980caa6adc7f17e055e16eb51b231df7e58a':'controllers_v9.py',
 '3ceca900d3490c29d9a87e01ac0aed0dbe50f4e4f4e43f3369c022bf7fd60718':'controllers_heading0.py'}
OLD="angle=np.arctan2(red[1],red[0]); orientation=R.from_euler('z',angle)\n        center=red+orientation.apply([-.10,0,0]); center[2]=.25\n"
HEADING="angle=0.0 if self.name.startswith('RedBoxUnder') else np.arctan2(red[1],red[0]); orientation=R.from_euler('z',angle)"
BASE_HEADING="angle=np.arctan2(red[1],red[0]); orientation=R.from_euler('z',angle)"

def compatible(env_name,recorded_sha):
    current=(ROOT/'controllers.py').read_bytes()
    if recorded_sha==hashlib.sha256(current).hexdigest():return True
    if recorded_sha not in SNAPSHOTS or env_name.split('/')[-1].startswith('RedBoxUnder'):return False
    snapshot=(ROOT/'development'/SNAPSHOTS[recorded_sha]).read_bytes()
    if hashlib.sha256(snapshot).hexdigest()!=recorded_sha:return False
    baseline=snapshot.decode().replace(HEADING,BASE_HEADING)
    block=(ROOT/'development/hook_plan_final.txt').read_text()
    # The replacement changes angle/lateral only inside RedBoxUnder's branch;
    # the non-under calculation stays radial, with lateral offset exactly zero.
    expected=baseline.replace(OLD,block)
    return baseline.count(OLD)==1 and expected==current.decode()
