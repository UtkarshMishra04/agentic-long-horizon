"""Analytical object-pose feedback helpers using only public robot state."""
import numpy as np
from scipy.spatial.transform import Rotation as R

def move_object(c, name, point, orientation, anchor=(0,0,0), n=150, tolerance=.008):
    point=np.asarray(point,float); anchor=np.asarray(anchor,float)
    for i in range(n):
        e,o=c.state(); pose=o[name]; actual=R.from_quat(pose[3:]); grip=R.from_quat(c.env.get_state()[23:27])
        error=point-(pose[:3]+actual.apply(anchor))
        change=orientation*actual.inv(); rv=change.as_rotvec(); angle=np.linalg.norm(rv)
        # Rotate about the controlled point, compensating the wrist lever arm.
        change=R.from_rotvec(rv*min(1,.12/max(angle,1e-9)))
        c.rot=(change*grip).as_rotvec()
        lever=e-(pose[:3]+actual.apply(anchor))
        shift=error*min(1,.018/max(np.linalg.norm(error),1e-9))
        c.step(e+shift+change.apply(lever)-lever)
        if np.linalg.norm(error)<tolerance and angle<.06 and i>12: break
