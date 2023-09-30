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

EvalGUI(policy=policy)