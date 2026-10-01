import argparse, json, math, time, os
os.environ.setdefault("LP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
import numpy as np
from scipy.spatial.transform import Rotation as R
import roboenvs
from shapely.geometry import Polygon, Point
from shapely.ops import unary_union
from tool_control import move_object

ORDERS = {'LiftRedBox-v0':['rack','lstick','red_box'], 'RedBoxOnRack-v0':['rack','lstick','red_box'], 'RedBoxUnderRack-v0':['rack','lstick','red_box'], 'RedBoxUnderRack-v1':['rack','lstick','red_box'], 'RedBoxToBlueSpot-v0':['lstick','red_box','blue_box'], 'RedBoxToBlueSpot-v1':['lstick','red_box','blue_box'], 'PackRack-v0':['rack','yellow_box','red_box','cyan_box'], 'PackRack-v1':['rack','blue_box','yellow_box','cyan_box'], 'PackRack-v2':['rack','blue_box','yellow_box','red_box','cyan_box']}
TOP=np.array([[0.,1,0],[1,0,0],[0,0,-1]])
class Done(Exception): pass
class Controller:
    def __init__(self,env,name,verbose=False):
        self.env=env; self.name=name.split('/')[-1]; self.names=ORDERS[self.name]; self.steps=0; self.success=False; self.verbose=verbose; self.rot=R.from_quat(env.get_state()[23:27]).as_rotvec(); self.closed=False; self.recorder=None
    def state(self):
        s=self.env.get_state(); return s[20:23], {n:s[27+i*7:34+i*7].copy() for i,n in enumerate(self.names)}
    def log(self,*args):
        if self.verbose: print(self.steps,*args,flush=True)
    def step(self,p):
        ob,r,t,tr,info=self.env.step(np.r_[p,self.rot,1 if self.closed else -1]); self.steps+=1
        if self.recorder: self.recorder(ob,dict(info,truncated=bool(tr)))
        if t or tr: self.success=t; raise Done()
    def move(self,p,n=90,tol=.007):
        p=np.asarray(p,float)
        target=self.state()[0].copy()
        for i in range(n):
            e,_=self.state(); d=p-e; remaining=p-target; target=target+remaining*min(1,.025/max(np.linalg.norm(remaining),1e-9)); self.step(target)
            if np.linalg.norm(d)<tol and i>=8 and (R.from_quat(self.env.get_state()[23:27])*R.from_rotvec(self.rot).inv()).magnitude()<.10: break
    def hold(self,n=15):
        p,_=self.state()
        for i in range(n): self.step(p)
    def choose_rotation(self,candidates,p):
        state=self.env.get_state()
        actual=R.from_quat(state[23:27]).as_matrix()@TOP.T
        current_yaw=np.arctan2(actual[1,0],actual[0,0])
        azimuth=np.arctan2(p[1],p[0])-np.arctan2(state[21],state[20])
        def score(rot):
            mat=rot.as_matrix()@TOP.T
            yaw=np.arctan2(mat[1,0],mat[0,0])
            delta=(yaw-current_yaw+np.pi)%(2*np.pi)-np.pi
            wrist=state[6]+azimuth-delta
            return abs(wrist)
        self.rot=min(candidates,key=score).as_rotvec()
    def yaw(self,a,p):
        self.choose_rotation([R.from_euler('z',a+k*np.pi/2)*R.from_matrix(TOP) for k in range(4)],p)
    def recover(self):
        e,_=self.state(); self.rot=R.from_quat(self.env.get_state()[23:27]).as_rotvec()
        self.move([e[0],e[1],.45])
        self.move([.50,0,.45])
        self.log('recovered',self.env.get_state()[:7].tolist(),self.state()[0].tolist())
    def pick(self,name):
        _,o=self.state(); p=o[name][:3]; self.log('pick',name,p.tolist()); self.closed=False
        self.recover()
        a=R.from_quat(o[name][3:]).as_euler('xyz')[2]; self.yaw(a,p)
        if np.linalg.norm(p[:2])>.77:
            radial=np.arctan2(p[1],p[0]); axis=np.array([np.sin(radial),-np.cos(radial),0.])
            tilt=1.10 if np.linalg.norm(p[:2])>.90 else .85
            self.choose_rotation([R.from_rotvec(axis*tilt)*R.from_euler('z',radial+k*np.pi)*R.from_matrix(TOP) for k in range(2)],p)
            self.move(p+np.array([-.13*np.cos(radial),-.13*np.sin(radial),.17]))
        else: self.move([p[0],p[1],.30])
        self.move(p+[0,0,.005]); self.log('at grasp',self.state()[0].tolist()); self.closed=True; self.hold(20)
        if np.linalg.norm(p[:2])>.77:
            self.move([p[0]*.78,p[1]*.78,.16])
        else: self.move([p[0],p[1],.30])
        _,o=self.state(); self.log('lifted',o[name][:3].tolist())
        return o[name][2]>.12
    def place(self,name,xy,z=.035):
        # Level the carried box over clear space before descending.
        self.recover()
        e,o=self.state()
        boxrot=R.from_quat(o[name][3:])
        desired=R.from_euler('z',boxrot.as_euler('xyz')[2])*R.from_euler('x',np.pi if boxrot.as_matrix()[2,2]<0 else 0)
        correction=desired*boxrot.inv()
        if correction.magnitude()>.12:
            self.move([.55, .05, .32])
            e,o=self.state(); boxrot=R.from_quat(o[name][3:])
            desired=R.from_euler('z',boxrot.as_euler('xyz')[2])*R.from_euler('x',np.pi if boxrot.as_matrix()[2,2]<0 else 0)
            self.rot=(desired*boxrot.inv()*R.from_quat(self.env.get_state()[23:27])).as_rotvec()
            self.move(e,n=45)
        e,o=self.state(); offset=o[name][:3]-e
        self.move([xy[0]-offset[0],xy[1]-offset[1],.32]); self.move(np.r_[xy,z+.008]-offset)
        for _ in range(35):
            e,o=self.state(); error=np.r_[xy,z+.005]-o[name][:3]
            self.step(e+np.clip(error,-.02,.02))
            if np.linalg.norm(error)<.005: break
        self.closed=False; self.hold(15); self.move([xy[0]-offset[0],xy[1]-offset[1],.32]); self.log('placed',name,self.state()[1][name][:3].tolist())
    def grasp_stick(self,grasp_x=-.1):
        e,o=self.state(); original=o['lstick'].copy()
        sr=R.from_quat(original[3:]); a=sr.as_euler('xyz')[2]
        grasp=original[:3]+sr.apply([grasp_x,-.09,0])
        self.closed=False; self.move([e[0],e[1],max(.35,e[2])])
        self.choose_rotation([R.from_euler('z',a+k*np.pi)*R.from_matrix(TOP) for k in range(2)],grasp)
        self.move([grasp[0],grasp[1],.24]); self.move(grasp+[0,0,.002])
        self.closed=True; self.hold(20); self.move([grasp[0],grasp[1],.28])
        self.log('stick lifted',self.state()[1]['lstick'][:3].tolist())
        return original
    def restore_stick(self,original):
        e,o=self.state(); self.move(e+[0,0,.22])
        orientation=R.from_quat(original[3:])
        move_object(self,'lstick',np.r_[original[:2],.25],orientation,n=120)
        move_object(self,'lstick',original[:3]+[0,0,.002],orientation,n=120)
        self.closed=False; self.hold(18);e,_=self.state();self.move(e+[0,0,.25])
    def park_stick_pose(self,original):
        _,o=self.state(); obstacles=[]
        for name,pose in o.items():
            if name=='lstick': continue
            if name=='rack':
                rr=R.from_quat(pose[3:]).as_matrix()[:2,:2]
                obstacles.append(Polygon(np.array([[-.11,-.16],[.11,-.16],[.11,.16],[-.11,.16]])@rr.T+pose[:2]))
            else: obstacles.append(self.footprint(name,pose))
        candidates=[]
        for x in [.4,.45,.5,.55,.6]:
            for y in [-.25,-.12,0,.12,.25]:
                for a in [R.from_quat(o['lstick'][3:]).as_euler('xyz')[2]]:
                    pose=np.r_[x,y,.022,R.from_euler('z',a).as_quat()]
                    shape=self.footprint('lstick',pose)
                    bounds=shape.bounds
                    if bounds[0]<.22 or bounds[2]>.9 or bounds[1]<-.46 or bounds[3]>.46: continue
                    clearance=min(shape.distance(obstacle) for obstacle in obstacles)
                    if clearance>.075:
                        candidates.append((np.linalg.norm(pose[:2]-original[:2])-.1*clearance,pose))
        return min(candidates,key=lambda item:item[0])[1] if candidates else original
    def hook_red(self):
        original=self.grasp_stick()
        red=self.state()[1]['red_box'][:3].copy()
        angle=np.arctan2(red[1],red[0]); lateral=0.0
        if self.name.startswith('RedBoxUnder'):
            _,objects=self.state(); rack=objects['rack']
            rack_rotation=R.from_quat(rack[3:]).as_matrix()[:2,:2]
            rack_shape=Polygon(np.array([[-.11,-.16],[.11,-.16],[.11,.16],[-.11,.16]])@rack_rotation.T+rack[:2])
            stick=objects['lstick']; ee,_=self.state()
            grip_local=R.from_quat(stick[3:]).inv().apply(ee-stick[:3])
            options=[]
            for candidate_angle in [angle,0,angle-.3,angle+.3,angle-.6,angle+.6]:
                rotation=R.from_euler('z',candidate_angle)
                for offset in [0,.06,-.06,.09,-.09]:
                    start=red+rotation.apply([-.10,offset,0]); start[2]=.025
                    grip=start+rotation.apply(grip_local)
                    if grip[0]<.25 or np.linalg.norm(grip[:2])>.79 or abs(grip[1])>.47: continue
                    clearance=1.0
                    for distance in [0,.08,.16,.25]:
                        center_test=start-rotation.apply([distance,0,0])
                        clearance=min(clearance,self.footprint('lstick',np.r_[center_test,rotation.as_quat()]).distance(rack_shape))
                    if clearance>.009:
                        options.append(((0 if candidate_angle==angle and offset==0 else 1+abs(candidate_angle)+4*abs(offset)),candidate_angle,offset))
            if options:
                _,angle,lateral=min(options)
        orientation=R.from_euler('z',angle)
        center=red+orientation.apply([-.10,lateral,0]); center[2]=.25
        move_object(self,'lstick',center,orientation,n=120)
        center[2]=.021; move_object(self,'lstick',center,orientation,n=150)
        center-=orientation.apply([.25,0,0]); move_object(self,'lstick',center,orientation,n=180)
        self.log('hooked',self.state()[1]['red_box'].tolist())
        self.restore_stick(self.park_stick_pose(original))
    def push_under(self):
        _,o=self.state();r=o['rack']; staging=r[:2]+[-.20,0]
        if np.linalg.norm(o['red_box'][:2]-staging)>.04:
            if not self.pick('red_box'): return
            self.place('red_box',staging)
        self.grasp_stick(.05)
        _,o=self.state(); red=o['red_box'];r=o['rack'];orientation=R.from_euler('z',0)
        center=np.array([red[0]-.24,red[1],.24])
        move_object(self,'lstick',center,orientation,n=120)
        center[2]=.037;move_object(self,'lstick',center,orientation,n=150)
        center[0]=r[0]-.25;move_object(self,'lstick',center,orientation,n=180)
        self.hold(15)
    def footprint(self,name,pose):
        if name=='lstick':
            rectangles=[(0,-.09,.20,.02),(.18,0,.02,.11)]
        else:
            h=.025 if name=='red_box' else .035
            rectangles=[(0,0,h,h)]
        rr=R.from_quat(pose[3:]).as_matrix()[:2,:2]
        return unary_union([Polygon(np.array([[x-hx,y-hy],[x+hx,y-hy],[x+hx,y+hy],[x-hx,y+hy]])@rr.T+pose[:2]) for x,y,hx,hy in rectangles])
    def spot_target(self):
        goal=self.env.get_goal()
        target=np.array(next(c['target_xy'] for c in goal['conditions'] if c['type']=='pos' and c['objects'][0]=='red_box'))
        _,o=self.state()
        obstacles=[self.footprint(n,o[n]) for n in ['lstick','blue_box']]
        candidates=[target+r*np.array([np.cos(a),np.sin(a)]) for r in [.13,.14,.12] for a in np.linspace(0,2*np.pi,48,endpoint=False)]
        candidates=[p for p in candidates if .25<p[0]<.78 and abs(p[1])<.43 and all(Point(p).distance(g)>.096 for g in obstacles)]
        if candidates: return max(candidates,key=lambda p:min(Point(p).distance(g) for g in obstacles)-.005*np.linalg.norm(p))
        # Create room at the goal by moving blue to an empty, reachable patch.
        obstacles=[self.footprint(n,o[n]) for n in ['lstick','red_box']]
        candidates=[np.array([x,y]) for x in np.linspace(.3,.65,8) for y in np.linspace(-.38,.38,13)]
        candidates=[p for p in candidates if p[0]>.42 and np.linalg.norm(p)<.72 and np.linalg.norm(p-target)>.23 and all(Point(p).distance(g)>.12 for g in obstacles)]
        if candidates and self.pick('blue_box'):
            self.place('blue_box',max(candidates,key=lambda p:min(Point(p).distance(g) for g in obstacles)))
        return target
    def run(self):
        try:
            home=np.array([.45,0,.40])
            self.choose_rotation([R.from_euler('z',k*np.pi/2)*R.from_matrix(TOP) for k in range(4)],home)
            self.move(home)
            for repeat in range(4):
                if 'lstick' in self.names and np.linalg.norm(self.state()[1]['red_box'][:2])>.84:
                    self.hook_red()
                if self.name.startswith('Lift'):
                    self.pick('red_box')
                elif self.name.startswith('RedBoxOn'):
                    if self.pick('red_box'): self.place('red_box',self.state()[1]['rack'][:2],.20)
                elif self.name.startswith('Pack'):
                    _,o=self.state(); rack=o['rack']; rr=R.from_quat(rack[3:]).as_matrix()[:2,:2]
                    slots=[rack[:2]+rr@np.array(v) for v in [(-.055,-.105),(.055,-.105),(-.055,.08),(.055,.08)]]
                    boxes=[n for n in self.names if n!='rack']; occupied=[o[n][:2] for n in boxes if o[n][2]>.14]
                    for name in boxes:
                        if self.state()[1][name][2]>.14: continue
                        slot=max(slots,key=lambda s:min([np.linalg.norm(s-v) for v in occupied]+[10]))
                        if self.pick(name): self.place(name,slot,.20); occupied.append(slot)
                elif self.name.startswith('RedBoxTo'):
                    target=self.spot_target()
                    if self.pick('red_box'): self.place('red_box',target)
                else:
                    self.push_under()
            while True: self.hold(20)
        except Done: return {'success':bool(self.success),'steps':self.steps}

def episode(name,seed,verbose=False):
    eid=name if '/' in name else 'roboenvs/'+name
    env=roboenvs.make(eid,control='absolute',cameras=('agentview',),image_size=8)
    try:
        _,info=env.reset(seed=seed); c=Controller(env,eid,verbose); result=c.run(); result.update(env=eid,seed=seed,scene_seed=info['scene_seed'],final_objects={n:v.tolist() for n,v in c.state()[1].items()},goal=env.get_goal()); return result
    finally: env.close()
if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('env',choices=list(ORDERS)); p.add_argument('--seed',type=int,default=0); p.add_argument('--verbose',action='store_true'); a=p.parse_args(); print(json.dumps(episode(a.env,a.seed,a.verbose)))
