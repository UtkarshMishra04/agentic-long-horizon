"""Check the completed public-interface solutions, evaluation, and video artifacts."""
import hashlib
import json
import py_compile
import runpy
import subprocess
from pathlib import Path
import numpy as np
import longhorizontamp
from controllers import ORDERS
from revision_compat import compatible

root=Path(__file__).resolve().parent
assert set(longhorizontamp.ENV_IDS)=={'LongHorizonTAMP/'+name for name in ORDERS}
files=list(root.glob('*.py'))+list((root/'solutions').glob('*.py'))
for path in files:py_compile.compile(str(path),doraise=True)
runpy.run_path(str(root/'audit_interface.py'),run_name='__main__')
rows=[json.loads(line) for line in (root/'results.jsonl').read_text().splitlines()]
clips=[json.loads(line) for line in (root/'videos/results.jsonl').read_text().splitlines()]
assert len(rows)==180 and len(clips)==45
helper=hashlib.sha256((root/'tool_control.py').read_bytes()).hexdigest()
for row in rows:
    assert 'error' not in row
    assert compatible(row['env'],row['controller_sha256'])
    assert row['tool_control_sha256']==helper
for clip in clips:
    assert compatible(clip['env'],clip['controller_sha256'])
    assert clip['frames']==clip['steps']+31
rng=np.random.RandomState(20260930)
expected_video_seeds={name:set(map(int,rng.choice(1000000,5,replace=False))) for name in ORDERS}
summary={}
for name in ORDERS:
    assert (root/'solutions'/(name+'.py')).is_file()
    group=[r for r in rows if r['env']=='LongHorizonTAMP/'+name]
    videos=[r for r in clips if r['env']==name]
    assert len(group)==20 and {r['seed'] for r in group}==set(range(0,20000,1000))
    assert len({r['scene_seed'] for r in group})==20
    assert len(videos)==5 and {r['seed'] for r in videos}==expected_video_seeds[name]
    assert len({r['scene_seed'] for r in videos})==5
    summary[name]=dict(evaluation_successes=sum(r['success'] for r in group),evaluation_episodes=20,
                       video_successes=sum(r['success'] for r in videos),video_episodes=5)
for row in clips+[{'video':str(root/'solutions_demo.mp4'),'frames':sum(r['frames'] for r in clips)}]:
    output=subprocess.check_output(['ffprobe','-v','error','-select_streams','v:0','-show_entries',
        'stream=nb_frames,width,height,r_frame_rate','-of','json',row['video']])
    stream=json.loads(output)['streams'][0]
    assert (stream['width'],stream['height'],stream['r_frame_rate'])==(384,416,'20/1')
    assert int(stream['nb_frames'])==row['frames']
assert (root/'RESULTS.md').is_file() and (root/'videos/INDEX.md').is_file()
report=dict(controller_sha256=hashlib.sha256((root/'controllers.py').read_bytes()).hexdigest(),
            tool_control_sha256=helper,environments=summary,
            evaluation_successes=sum(r['success'] for r in rows),evaluation_episodes=len(rows),
            video_successes=sum(r['success'] for r in clips),video_episodes=len(clips),
            video_frames=sum(r['frames'] for r in clips),video_seconds=sum(r['frames'] for r in clips)/20,
            checks=['nine environment IDs and runnable wrappers','Python compilation','public environment API audit',
                    '20 distinct requested and actual seeds per environment','source revision compatibility',
                    'five distinct video seeds per environment','every action frame retained','45 clip and combined-video frame counts'])
(root/'validation.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
