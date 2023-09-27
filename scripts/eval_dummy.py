import os
from datetime import date
from r2d2.controllers.oculus_controller import VRPolicy
from r2d2.robot_env import RobotEnv
from r2d2.user_interface.data_collector import DataCollecter
from r2d2.user_interface.eval_gui import EvalGUI
import numpy as np


class Policy:
    
    def __init__(self):
        print("new policy created")
    
    def load_goal_img_dir(self, goal_img_dir):
        print(f"loaded goal imag dir: {goal_img_dir}")
    
    def load_lang_conditioning(self, text):
        print(f"loaded text: {text}")

    def forward(self, obs):
        return np.zeros((7))

policy = Policy()

env = RobotEnv()
controller = VRPolicy()

dir_path = os.path.dirname(os.path.realpath(__file__))
data_dir = os.path.join(dir_path, "../data")
eval_traj_dir = os.path.join(data_dir, "evals", str(date.today()))

data_col = DataCollecter(env = env, controller=controller, policy=policy, save_data=True, save_traj_dir=eval_traj_dir)
EvalGUI(policy=policy, robot=data_col)