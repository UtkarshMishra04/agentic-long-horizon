"""Summarize recorded public-interface results and explain failed goal predicates."""
import argparse
import collections
import json
import numpy as np
from scipy.spatial.transform import Rotation as R
from shapely.geometry import Polygon
from shapely.ops import unary_union

def shape(name,pose):
    if name=='lstick': rectangles=[(0,-.09,.20,.02),(.18,0,.02,.11)]
    elif name=='rack': rectangles=[(0,0,.11,.16)]
    else:
        h=.025 if name=='red_box' else .035
        rectangles=[(0,0,h,h)]
    rr=R.from_quat(pose[3:]).as_matrix()[:2,:2]
    return unary_union([Polygon(np.array([[x-hx,y-hy],[x+hx,y-hy],[x+hx,y+hy],[x-hx,y+hy]])@rr.T+pose[:2]) for x,y,hx,hy in rectangles])

def reasons(record):
    if record.get('error'): return [record['error']]
    objects={name:np.array(p) for name,p in record['final_objects'].items()}
    messages=[]
    for name,pose in objects.items():
        if pose[2]<-.1: messages.append(name+' fell off the table')
        elif name=='rack' and (pose[2]<.10 or R.from_quat(pose[3:]).as_matrix()[2,2]<.9): messages.append('rack is overturned or tilted')
    for condition in record['goal']['conditions']:
        typ=condition['type']; name=condition['objects'][0]; pose=objects[name]
        if typ=='pos':
            distance=np.linalg.norm(pose[:2]-condition['target_xy'])
            if distance>condition['tolerance']: messages.append('%s position error %.3f m exceeds %.3f m'%(name,distance,condition['tolerance']))
        elif typ=='inworkspace':
            if pose[0]<condition['x_min'] or np.linalg.norm(pose[:2])>=condition['radius']: messages.append(name+' is outside the required workspace')
        elif typ=='on':
            if abs(R.from_quat(pose[3:]).as_matrix()[2,2])<.99: messages.append(name+' is tipped')
            parent=condition['objects'][1]
            height=(.035 if name!='lstick' else .02)+(objects[parent][2] if parent in objects else 0)
            if abs(pose[2]-height)>.04: messages.append(name+' is not at the required support height')
            if parent=='rack' and shape(name,pose).intersection(shape(parent,objects[parent])).area<1e-6: messages.append(name+' is outside the rack footprint')
        elif typ=='under':
            rack=condition['objects'][1]; area=shape(name,pose)
            fraction=area.intersection(shape(rack,objects[rack])).area/max(area.area,1e-9)
            if fraction<condition['min_fraction']:messages.append('%s rack overlap %.1f%% is below %.1f%%'%(name,100*fraction,100*condition['min_fraction']))
        elif typ=='free':
            for other,p in objects.items():
                if name==other:continue
                kind='box' if other.endswith('_box') else other
                threshold=condition['min_distance'].get(kind,0)
                if threshold and shape(name,pose).distance(shape(other,p))<threshold: messages.append(name+' is too close to '+other)
        elif typ=='inhand':messages.append('red_box was not held or lifted at the time limit')
    return list(dict.fromkeys(messages)) or ['Goal still false; inspect final poses and video for contact or alignment failure']

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('results',nargs='?',default='/workspace/results.jsonl')
    parser.add_argument('--output',default='/workspace/failure_analysis.json')
    args=parser.parse_args()
    records=[json.loads(line) for line in open(args.results)]
    failures=[dict(env=r['env'],seed=r['seed'],scene_seed=r.get('scene_seed'),reasons=reasons(r)) for r in records if not r['success']]
    with open(args.output,'w') as output:json.dump(failures,output,indent=2)
    for env in sorted(set(r['env'] for r in records)):
        group=[r for r in records if r['env']==env]
        print(env,'%d/%d'%(sum(r['success'] for r in group),len(group)))
    print(json.dumps(failures,indent=2))
