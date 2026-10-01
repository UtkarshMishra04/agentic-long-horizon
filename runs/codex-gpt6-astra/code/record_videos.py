"""Record five reproducibly random seeds per task, without omitting failed runs."""
import argparse
import concurrent.futures
import json
import hashlib
import os
import subprocess
import time
os.environ.setdefault('LP_NUM_THREADS', '1')
os.environ.setdefault('OPENBLAS_NUM_THREADS', '1')
os.environ.setdefault('OMP_NUM_THREADS', '1')
import numpy as np
from PIL import Image, ImageDraw
import roboenvs
from controllers import Controller, ORDERS
from revision_compat import compatible
SOURCE_SHA256=hashlib.sha256(open(os.path.join(os.path.dirname(__file__),"controllers.py"),"rb").read()).hexdigest()

class Video:
    def __init__(self, path, label):
        self.label = label
        self.frames = 0
        self.last = None
        self.process = subprocess.Popen([
            'ffmpeg', '-v', 'error', '-y', '-f', 'rawvideo', '-pixel_format', 'rgb24',
            '-video_size', '384x416', '-framerate', '20', '-i', '-', '-an',
            '-c:v', 'libx264', '-threads', '1', '-preset', 'fast', '-crf', '23',
            '-pix_fmt', 'yuv420p', path], stdin=subprocess.PIPE)
    def frame(self, observation, info):
        canvas = Image.new('RGB', (384,416), 'black')
        canvas.paste(Image.fromarray(observation['agentview_image']).resize((384,384), Image.BILINEAR), (0,32))
        draw = ImageDraw.Draw(canvas)
        draw.text((5,2), self.label, fill='white')
        draw.text((5,17), 'step %d  %s' % (info.get('step',0), 'SUCCESS' if info.get('success') else ('TIME LIMIT' if info.get('truncated') else 'running')), fill='white')
        self.last=np.asarray(canvas).tobytes()
        self.process.stdin.write(self.last)
        self.frames += 1
    def close(self):
        if self.last:
            for _ in range(30): self.process.stdin.write(self.last)
            self.frames += 30
        self.process.stdin.close()
        if self.process.wait() != 0: raise RuntimeError('ffmpeg failed')

def record(job):
    name, seed, directory = job
    path = os.path.join(directory, '%s_seed%d.mp4' % (name,seed))
    env = roboenvs.make('roboenvs/'+name,control='absolute',cameras=('agentview',),image_size=256)
    video = None
    try:
        ob, info = env.reset(seed=seed)
        video = Video(path, '%s seed=%d scene=%d' % (name,seed,info['scene_seed']))
        video.frame(ob,info)
        controller = Controller(env,name)
        controller.recorder = video.frame
        result = controller.run()
        result.update(env=name,seed=seed,scene_seed=info['scene_seed'],video=path,frames=video.frames+30,controller_sha256=SOURCE_SHA256)
        return result
    finally:
        if video: video.close()
        env.close()

if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workers',type=int,default=6)
    parser.add_argument('--random-seed',type=int,default=20260930)
    parser.add_argument('--output',default='/workspace/videos')
    parser.add_argument('--env',nargs='+',choices=list(ORDERS),default=list(ORDERS))
    parser.add_argument('--resume',action='store_true')
    args=parser.parse_args()
    os.makedirs(args.output,exist_ok=True)
    rng=np.random.RandomState(args.random_seed)
    jobs=[(name,int(seed),args.output) for name in ORDERS for seed in rng.choice(1000000,5,replace=False)]
    with open(os.path.join(args.output,'seeds.json'),'w') as f: json.dump(jobs,f,indent=2)
    jobs=[j for j in jobs if j[0] in args.env]
    if args.resume:
        manifest=os.path.join(args.output,'results.jsonl')
        previous=[json.loads(line) for line in open(manifest)] if os.path.exists(manifest) else []
        assert all(compatible(r['env'],r.get('controller_sha256')) for r in previous), 'Cannot resume videos from another controller revision'
        completed={(r['env'],r['seed']) for r in previous if os.path.exists(r['video'])}
        jobs=[j for j in jobs if (j[0],j[1]) not in completed]
    with open(os.path.join(args.output,'results.jsonl'),'a' if args.resume else 'w',buffering=1) as f, concurrent.futures.ProcessPoolExecutor(args.workers) as pool:
        futures=[pool.submit(record,j) for j in jobs]
        for future in concurrent.futures.as_completed(futures):
            result=future.result()
            f.write(json.dumps(result)+'\n');print(json.dumps(result),flush=True)
