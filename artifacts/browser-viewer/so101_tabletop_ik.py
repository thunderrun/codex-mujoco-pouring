"""Position and orientation inverse kinematics for the tabletop SO-101 arm."""

import mujoco
import numpy as np


# A point between the tips of the fixed and moving jaws at a useful gripping depth.
PINCH_OFFSET = np.array([0.007, 0.0, -0.092])


def _unit(vector):
    vector = np.asarray(vector, dtype=np.float64)
    if vector.shape != (3,) or not np.all(np.isfinite(vector)):
        raise ValueError("expected a finite three-dimensional vector")
    length = np.linalg.norm(vector)
    if length < 1e-12:
        raise ValueError("direction must be nonzero")
    return vector / length


def _pose(data, gripper_body):
    rotation = data.xmat[gripper_body].reshape(3, 3)
    point = data.xpos[gripper_body] + rotation @ PINCH_OFFSET
    return point, -rotation[:, 2], rotation[:, 0]


def solve(model, arm_qpos, position, closing_axis):
    """Return five arm joint targets in radians for the selected pinch point."""
    target = np.asarray(position, dtype=float)
    approach = np.array([0., 0., -1.])
    axis = _unit(closing_axis)
    closing_axis = _unit(axis - np.dot(axis, approach) * approach)
    data = mujoco.MjData(model)
    joint_ids = model.actuator_trnid[:5, 0]
    joint_addresses = model.jnt_qposadr[joint_ids]
    velocity_addresses = model.jnt_dofadr[joint_ids]
    data.qpos[joint_addresses] = arm_qpos
    lower, upper = model.actuator_ctrlrange[:5].T
    gripper_body = model.body("gripper").id
    jacp = np.empty((3, model.nv))
    jacr = np.empty((3, model.nv))

    def evaluate(joints):
        data.qpos[joint_addresses] = joints
        mujoco.mj_kinematics(model, data)
        point, forward, lateral = _pose(data, gripper_body)
        parts = [target - point, 0.060 * (approach - forward)]
        parts.append(0.035 * (closing_axis - lateral))
        return np.concatenate(parts), point, forward, lateral

    current = np.clip(data.qpos[joint_addresses], lower, upper)
    yaw = np.arctan2(target[1], target[0])
    home = np.deg2rad([0, -60, 60, 35, 0])
    home[0] = yaw
    starts = [current]
    for roll in (0, 90, -90, 160, -160):
        seed = home.copy()
        seed[4] = np.deg2rad(roll)
        starts.append(np.clip(seed, lower, upper))

    best_error = float("inf")
    best_joints = current
    for joints in starts:
        for _ in range(80):
            residual, point, forward, lateral = evaluate(joints)
            error = np.linalg.norm(residual)
            if error < best_error:
                best_error = error
                best_joints = joints.copy()
            if error < 0.00035:
                break

            mujoco.mj_comPos(model, data)
            mujoco.mj_jac(model, data, jacp, jacr, point, gripper_body)
            angular = jacr[:, velocity_addresses].T
            blocks = [jacp[:, velocity_addresses], 0.060 * np.cross(angular, forward).T]
            blocks.append(0.035 * np.cross(angular, lateral).T)
            jacobian = np.vstack(blocks)
            hessian = jacobian.T @ jacobian + 8e-6 * np.eye(5)
            step = np.clip(np.linalg.solve(hessian, jacobian.T @ residual), -0.32, 0.32)
            for fraction in (1.0, 0.5, 0.25, 0.125):
                candidate = np.clip(joints + fraction * step, lower, upper)
                if np.linalg.norm(evaluate(candidate)[0]) < error:
                    joints = candidate
                    break
            else:
                break
        if best_error < 0.00035:
            break

    _, solved, forward, lateral = evaluate(best_joints)
    if np.linalg.norm(solved - target) > 0.004 or np.dot(forward, approach) < 0.98:
        raise ValueError("Selected pinch point is outside the arm workspace.")
    if np.dot(lateral, closing_axis) < 0.98:
        raise ValueError("Selected jaw angle cannot be reached at that pixel.")
    return best_joints
