"""Validate and concatenate the complete 45-episode rendered demonstration."""
import argparse
import json
from pathlib import Path
import subprocess
from controllers import ORDERS

if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory',default='/workspace/videos')
    parser.add_argument('--output',default='/workspace/solutions_demo.mp4')
    args=parser.parse_args()
    directory=Path(args.directory)
    records=[json.loads(line) for line in (directory/'results.jsonl').read_text().splitlines()]
    records=sorted(records,key=lambda row:(list(ORDERS).index(row['env']),row['seed']))
    assert len(records)==45, 'Need all 45 completed recordings'
    for name in ORDERS:
        assert len({r['seed'] for r in records if r['env']==name})==5, name
    total_frames=0
    for row in records:
        output=subprocess.check_output(['ffprobe','-v','error','-select_streams','v:0',
             '-show_entries','stream=nb_frames,width,height,r_frame_rate','-of','json',row['video']])
        stream=json.loads(output)['streams'][0]
        assert (stream['width'],stream['height'])==(384,416)
        assert int(stream['nb_frames'])==row['frames'], (row['video'],stream,row['frames'])
        assert row['frames']==row['steps']+31, 'Missing action frames'
        assert stream['r_frame_rate']=='20/1'
        total_frames+=row['frames']
    listing=directory/'concat.txt'
    listing.write_text(''.join("file '%s'\n" % Path(r['video']).resolve() for r in records))
    metadata=directory/'chapters.ffmetadata'
    chapters=[';FFMETADATA1','title=RoboEnvs deterministic controller demonstrations']
    start=0
    for row in records:
        end=start+row['frames']*50
        chapters.extend(['[CHAPTER]','TIMEBASE=1/1000','START=%d'%start,'END=%d'%end,
                         'title=%s | seed %d | %s'%(row['env'],row['seed'],'SUCCESS' if row['success'] else 'TIME LIMIT')])
        start=end
    metadata.write_text('\n'.join(chapters)+'\n')
    subprocess.run(['ffmpeg','-v','error','-y','-f','concat','-safe','0','-i',str(listing),
                    '-f','ffmetadata','-i',str(metadata),'-map_metadata','1','-map_chapters','1',
                    '-c','copy','-movflags','+faststart',args.output],check=True)
    chapter_probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_chapters','-of','json',args.output]))
    assert len(chapter_probe['chapters'])==45
    output=subprocess.check_output(['ffprobe','-v','error','-select_streams','v:0',
              '-show_entries','stream=nb_frames','-of','json',args.output])
    assert int(json.loads(output)['streams'][0]['nb_frames'])==total_frames
    index=['# Rendered demonstrations\n',
           'Five seeds per task selected by NumPy RandomState(20260930), without screening for success. ',
           'Every action step is shown at 20 frames per second, with a final 1.5-second hold. ',
           'The combined video is `../solutions_demo.mp4`, with one seekable chapter per episode.\n',
           '| Task | Requested seed | Actual scene seed | Outcome | Steps | Video |',
           '|---|---:|---:|---|---:|---|']
    for r in records:
        index.append('| %s | %d | %d | %s | %d | [%s](%s) |' %
            (r['env'],r['seed'],r['scene_seed'],'Success' if r['success'] else 'Time limit',
             r['steps'],Path(r['video']).name,Path(r['video']).name))
    (directory/'INDEX.md').write_text('\n'.join(index)+'\n')
    print(json.dumps(dict(clips=45,frames=total_frames,seconds=total_frames/20,combined=args.output)))
