from datetime import date
import numpy as np
import tkinter as tk


from tkinter.font import *
from tkinter import *
from r2d2.user_interface.gui import *
from r2d2.misc.time import time_ms

dir_path = os.path.dirname(os.path.realpath(__file__))
data_dir = os.path.join(dir_path, "../../data")
LAST_N_GOALS = 5

_DEFAULT_RESOLUTION = "1500x1200"
_ESCAPE_KEY = "<Escape>"

# create a string enum for conditioning: goal and language
class Condition:
    GOAL = "goal"
    LANGUAGE = "language"

class EvalGUI(tk.Tk):
    def __init__(self, policy, robot=None, fullscreen=False):
        # Initialize #
        super().__init__()
        self.policy = policy
        self.geometry(_DEFAULT_RESOLUTION)
        self.attributes("-fullscreen", fullscreen)
        self.bind(_ESCAPE_KEY, lambda e: self.destroy())

        # Prepare Relevent Items #
        self.num_eval_trials = 0
        self.cam_ids = list(robot.cam_ids)
        self.camera_order = np.arange(robot.num_cameras)
        self.time_index = None
        self.robot = robot
        self.num_traj_saved = 0
        self.info = {
            "current_task": "",
            "eval_conditioning": [], # radio button
            "user": "",
        }
        self.eval_traj_dir = os.path.join(data_dir, "evals", str(date.today()))
        if not os.path.isdir(self.eval_traj_dir):
            os.makedirs(self.eval_traj_dir)

        self.eval_goal_dirs = []
        # populate from past goal dirs
        self.fetch_goal_directories()
        # list all folders in eval_traj_dir

        if not os.path.isdir(self.eval_traj_dir):
            os.makedirs(self.eval_traj_dir)

        # Create Resizable Container #
        container = tk.Frame(self)
        container.pack(side="top", fill="both", expand=True)
        container.grid_rowconfigure(0, weight=1)
        container.grid_columnconfigure(0, weight=1)

                # Organize Frame Dict #
        self.frames = {}
        self.curr_frame = None
        for F in (
            CameraPage,
            CanRobotResetPage,
            CaptureGoal,
            ControllerOffPage,
            EnlargedImagePage,
            EvalConfigurationPage,
            RequestedBehaviorPage,
            RobotResetPage,

        ):
            self.frames[F] = F(container, self)
            self.frames[F].grid(row=0, column=0, sticky="nsew")

        post_reset_page = EvalConfigurationPage
        self.frames[CanRobotResetPage].set_next_page(post_reset_page)
        
        # Listen For Robot Reset #
        self.enter_presses = 0
        self.bind("<KeyPress-Return>", self.robot_reset, add="+")
        self.refresh_enter_variable()

        # Listen For Robot Controls #
        info_thread = threading.Thread(target=self.listen_for_robot_info)
        info_thread.daemon = True
        info_thread.start()

        # Update Camera Feed #
        self.camera_feed = None
        camera_thread = threading.Thread(target=self.update_camera_feed)
        camera_thread.daemon = True
        camera_thread.start()
        

        # Start Program! #
        self.last_frame_change = 0
        self.show_frame(EvalConfigurationPage)
        self.update_time_index()
        self.mainloop()

    def show_frame(self, frame_id, refresh_page=True, wait=False):
        if time.time() - self.last_frame_change < 0.1:
            return
        self.focus()

        self.last_frame_change = time.time()
        self.curr_frame, old_frame = self.frames[frame_id], self.curr_frame

        if hasattr(old_frame, "exit_page"):
            old_frame.exit_page()
        if hasattr(self.curr_frame, "initialize_page") and refresh_page:
            # self.show_frame(EvalConfigurationPage)
            self.curr_frame.initialize_page()

        if wait:
            self.after(100, self.curr_frame.tkraise)
        else:
            self.curr_frame.tkraise()

        if hasattr(self.curr_frame, "launch_page"):
            self.after(100, self.curr_frame.launch_page)

    def swap_img_order(self, i, j):
        self.camera_order[i], self.camera_order[j] = self.camera_order[j], self.camera_order[i]

    def set_img(self, i, widget=None, width=None, height=None, use_camera_order=True):
        index = self.camera_order[i] if use_camera_order else i
        if self.camera_feed is None:
            return
        else:
            img = self.camera_feed[index]
        img = Image.fromarray(img)
        if width is not None:
            img = ImageOps.contain(img, (width, height), Image.Resampling.LANCZOS)
        img = ImageTk.PhotoImage(img)
        widget.configure(image=img)
        widget.image = img

    def get_goal_img_snapshots(self, idxs=[]):
        if self.camera_feed is None:
            return
        else:
            if not idxs: idxs = [i for i in range(len(self.camera_feed))]
            current_ts = time_ms()
            eval_traj_dir = f"{self.eval_traj_dir}/goals/{current_ts}"
            os.makedirs(eval_traj_dir) 
            for idx in idxs:
                img = self.camera_feed[idx]
                img = Image.fromarray(img)
                # save pil image to disk
                img.save(f"{eval_traj_dir}/{idx}.png")

            self.eval_goal_dirs.append(eval_traj_dir)
            self.frames[EvalConfigurationPage].update_goal_radio_btns()
            self.frames[EvalConfigurationPage].toggle_capture_goal()

    def fetch_goal_directories(self):
        main_goal_dir = f"{self.eval_traj_dir}/goals"
        if not os.path.isdir(main_goal_dir):
            os.makedirs(main_goal_dir)

        for folder in sorted(os.listdir(main_goal_dir)):
            # get full path of folder
            folder = os.path.join(main_goal_dir, folder)
            print(f"found goal folder: {folder}")
            self.eval_goal_dirs.append(folder)

    def update_time_index(self):
        if self.time_index is not None:
            self.time_index = (self.time_index + 1) % len(self.last_traj)
        self.after(50, self.update_time_index)

    def robot_reset(self, event):
        self.enter_presses += 1
        if self.enter_presses == 25:
            self.enter_presses = -50
            self.frames[RobotResetPage].set_home_frame(type(self.curr_frame))
            self.show_frame(RobotResetPage)

    def refresh_enter_variable(self):
        self.enter_presses = 0
        self.after(3000, self.refresh_enter_variable)

    def listen_for_robot_info(self):
        last_was_false = True
        controller_on = True
        while True:
            time.sleep(0.1)
            info = self.robot.get_user_feedback()
            trigger = info["success"] or info["failure"]
            if info["success"] and last_was_false:
                self.event_generate("<<KeyRelease-controllerA>>")
            if info["failure"] and last_was_false:
                self.event_generate("<<KeyRelease-controllerB>>")
            if trigger and last_was_false:
                self.event_generate("<<KeyRelease-controller>>")

            # if info["controller_on"] < controller_on:
            #     self.show_frame(ControllerOffPage)

            last_was_false = not trigger
            controller_on = info["controller_on"]

    def update_camera_feed(self, sleep=0.05):
        while True:
            try:
                self.camera_feed, self.cam_ids = self.robot.get_camera_feed()
            except:
                pass
            time.sleep(sleep)


class EvalConfigurationPage(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        # Update Based Off Activity #
        self.controller.bind("<KeyRelease>", self.moniter_keys, add="+")
        self.controller.bind("<ButtonRelease-1>", self.moniter_keys, add="+")

        # Title #
        title_lbl = Label(self, text="Eval Configuration", font=Font(size=30, weight="bold"))
        title_lbl.place(relx=0.5, rely=0.05, anchor="n")

        pos_dict = {
            "goal conditioning": (0.25, 0.25),
        }
        self.conditioning_dict = defaultdict(BooleanVar)

        conditioning = ["image", "language"]
        toggle_funcs = [self.toggle_capture_goal, self.toggle_text_box]
        for i, key in enumerate(pos_dict):
            x_pos, y_pos = pos_dict[key]
            group_lbl = tk.Label(self, text=key + ":", font=Font(size=20, underline=True))
            group_lbl.place(relx=x_pos, rely=y_pos)
            
            for i, key in enumerate(conditioning):
                task_ckbox = tk.Checkbutton(self, text=key, font=Font(size=15), variable=self.conditioning_dict[key], command=toggle_funcs[i])
                task_ckbox.place(relx=x_pos + 0.01, rely=y_pos + (i + 1) * 0.04)


        # Goal Conditioning #            
        self.goal_dir_label = tk.Label(self, text="last five goal directories" + ":", font=Font(size=20, underline=True))
        
        # create selectable tk radio buttons for all items in self.eval_goal_dirs
        self.radio_buttons = []
        self.selected_goal_dir_idx = IntVar()
        self.update_goal_radio_btns()
        
        # Free Response Tasks #
        self.lang_text_lbl = tk.Label(self, text="Enter the text for language conditioning", font=Font(size=20, underline=True))
        self.lang_text = tk.Text(self, height=4, width=25, font=Font(size=15))
        self.lang_text_x = 0.5
        self.lang_text_y = 0.29

        self.toggle_text_box()        

         # Ready Button #
        collect_btn = tk.Button(
            self,
            text="evaluate",
            highlightbackground="green",
            font=Font(size=15, weight="bold"),
            height=1,
            width=8,
            borderwidth=5,
            command=self.eval_robot,
        )
        collect_btn.place(relx=0.46, rely=0.5)

        # Practice Button #
        self.capture_goal_btn = tk.Button(
            self,
            text="capture\nnew goal",
            highlightbackground="green",
            font=Font(size=12, weight="bold"),
            height=1,
            width=9,
            borderwidth=5,
            command=self.practice_robot,
        )

    def update_goal_radio_btns(self):
        # remove the old radio buttons
        for i in range(len(self.radio_buttons)):
            self.radio_buttons[i].place_forget()
        self.radio_buttons = []
        for i, folder in enumerate(self.controller.eval_goal_dirs[::-1][:LAST_N_GOALS]):
            # strip off everything before ../data
            folder = folder.split("data/")[-1]
            # change self.selected_goal_dir_idx to the index of the selected radio button
            self.radio_buttons.append(Radiobutton(self, text=folder, variable=self.selected_goal_dir_idx, value=i, command=self.goal_img_changed))

    def goal_img_changed(self):
        print(f"goal img changed to {self.controller.eval_goal_dirs[::-1][self.selected_goal_dir_idx.get()]}")
        if self.controller.policy is not None:
            self.controller.policy.load_goal_img_dir(self.controller.eval_goal_dirs[::-1][self.selected_goal_dir_idx.get()])

    def place_image_gc_elements(self):
        self.goal_dir_label.place(relx=0.5, rely=0.25)
        for i in range(len(self.radio_buttons)):
            self.radio_buttons[i].place(relx=self.lang_text_x, rely=self.lang_text_y + i * 0.02)
        self.capture_goal_btn.place(relx=self.lang_text_x + 0.04, rely=self.lang_text_y + 0.12)

    def forget_image_gc_elements(self):
        self.goal_dir_label.place_forget()
        for i in range(len(self.radio_buttons)):
            self.radio_buttons[i].place_forget()
        self.capture_goal_btn.place_forget()

    def toggle_text_box(self):
        if self.conditioning_dict["language"].get():
            self.lang_text_lbl.place(relx=self.lang_text_x, rely=self.lang_text_y-0.04)
            self.lang_text.place(relx=self.lang_text_x, rely=self.lang_text_y)
        else:
            self.lang_text_lbl.place_forget()
            self.lang_text.place_forget()

    def toggle_capture_goal(self):
        if self.conditioning_dict["image"].get():
            self.place_image_gc_elements()
        else:
            self.forget_image_gc_elements()

    def moniter_keys(self, event):
        if self.controller.curr_frame != self:
            return

        # Toggle Camera View
        if event.keysym in ["Shift_L", "Shift_R"]:
            self.controller.frames[CameraPage].set_home_frame(SceneConfigurationPage)
            self.controller.show_frame(CameraPage, wait=True)

    def practice_robot(self):
        self.controller.frames[CaptureGoal].set_mode("practice_traj")
        self.controller.show_frame(CaptureGoal, wait=True)

    def eval_robot(self):

        # set the goal conditioning
        if self.controller.policy is not None:
            self.controller.policy.language_conditioning = self.lang_text.get('1.0', 'end-1c')
        
        print(f"language conditioning: {self.lang_text.get('1.0', 'end-1c')}")
        if self.controller.eval_goal_dirs:
            print(f"goal img dir: {self.controller.eval_goal_dirs[::-1][self.selected_goal_dir_idx.get()]}")

        self.controller.frames[CaptureGoal].set_mode("traj")
        self.controller.show_frame(CaptureGoal, wait=True)



class CaptureGoal(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        self.n_rows = 1 if len(self.controller.camera_order) <= 2 else 2
        self.n_cols = math.ceil(len(self.controller.camera_order) / self.n_rows)

        # Moniter Key Events #
        self.controller.bind("<KeyRelease>", self.moniter_keys, add="+")
        self.controller.bind("<<KeyRelease-controller>>", self.moniter_keys, add="+")

        # Page Variables #
        self.title_str = StringVar()
        self.instr_str = StringVar()
        self.mode = "live"

        # Title #
        title_lbl = Label(self, textvariable=self.title_str, font=Font(size=30, weight="bold"))
        title_lbl.place(relx=0.5, rely=0.02, anchor="n")

        # Instructions #
        instr_lbl = tk.Label(self, textvariable=self.instr_str, font=Font(size=24, slant="italic"))
        instr_lbl.place(relx=0.5, rely=0.06, anchor="n")

        # Timer #
        self.timer_on = False
        self.time_str = StringVar()
        self.timer = tk.Button(
            self,
            textvariable=self.time_str,
            highlightbackground="black",
            font=Font(size=40, weight="bold"),
            padx=3,
            pady=5,
            borderwidth=10,
        )

        # Image Variables #
        self.image_boxes = []

        # Create Image Grid #
        for i in range(self.n_rows):
            self.rowconfigure(i, weight=1)
            for j in range(self.n_cols):
                if (i * self.n_cols + j) >= len(self.controller.camera_order):
                    continue
                self.columnconfigure(j, weight=1)

                # Add Image Box #
                button = tk.Button(
                    # self, height=0, width=0, highlightbackground='red', highlightthickness=5, command=lambda idx=(i * self.n_cols + j): self.update_image_grid(idx)
                    self, height=0, width=0, command=lambda idx=(i * self.n_cols + j): self.update_image_grid(idx)
                )
                button.grid(row=i, column=j, sticky="s" if self.n_rows > 1 else "")
                self.image_boxes.append(button)

                # Start Image Thread #
                camera_thread = threading.Thread(target=lambda idx=(i * self.n_cols + j): self.update_camera_feed(idx))
                camera_thread.daemon = True
                camera_thread.start()

        # if the mode is capture goal, add capture button
        self.capture_goal_btn = tk.Button(
            self,
            text="Capture",
            # highlightbackground="red",
            font=Font(size=30, weight="bold"),
            padx=3,
            pady=5,
            borderwidth=10,
            command=lambda save=False: self.controller.get_goal_img_snapshots(),
        )

        self.clicked_ids = []
        # select all cameras by default
        if self.mode != 'traj':
            self.capture_goal_btn.place(relx=0.45, rely=0.55)
            for i in range(0, len(self.controller.camera_order)):
                self.update_image_grid(i)

        # Moniter Key Events only when this page is shown#
        self.controller.bind("<<KeyRelease-controllerA>>", self.press_A, add="+")
        self.controller.bind("<<KeyRelease-controllerB>>", self.press_B, add="+")
        

    def is_page_inactive(self):
        zoom = self.controller.frames[EnlargedImagePage]
        page_inactive = self.controller.curr_frame not in [self, zoom]
        return page_inactive

    def press_A(self, event):
        if self.is_page_inactive() or self.mode == 'traj':
            return
        self.controller.get_goal_img_snapshots()

    def press_B(self, event):
        if self.is_page_inactive() or self.mode == 'traj':
            return
        self.controller.show_frame(EvalConfigurationPage)

    def update_image_grid(self, i):
        if i not in self.clicked_ids:
            self.clicked_ids.append(i)
            # self.image_boxes[i].config(highlightbackground="green")
        else:
            # self.image_boxes[i].config(highlightbackground="red")
            # remove i
            self.clicked_ids.remove(i)

    def update_camera_feed(self, i, w_coeff=1.0, h_coeff=1.0):
        while True:
            not_active = self.controller.curr_frame != self
            not_ready = len(self.controller.camera_order) != len(self.controller.cam_ids)
            if not_active or not_ready:
                time.sleep(0.05)
                continue

            w, h = max(self.winfo_width(), 100), max(self.winfo_height(), 100)
            img_w = int(w / self.n_cols * w_coeff)
            img_h = int(h / self.n_rows * h_coeff)

            self.controller.set_img(i, widget=self.image_boxes[i], width=img_w, height=img_h)

    def moniter_keys(self, event):
        zoom = self.controller.frames[EnlargedImagePage]
        page_inactive = self.controller.curr_frame not in [self, zoom]
        if page_inactive:
            return

        shift = event.keysym in ["Shift_L", "Shift_R"]

        if self.mode == "live" and shift:
            self.controller.show_frame(self.home_frame, refresh_page=False)

    def initialize_page(self):
        # Clear Widges #
        self.timer.place_forget()

        # Update Text #
        if self.mode != 'traj':
            self.title_str.set("Goal Conditioning")
            self.instr_str.set("press A to capture goal\n press B to go back to eval configuration page")
        else:
            self.title_str.set("Evaluating")
            self.instr_str.set("press A to save eval as success\n press B to save eval as failure")

        # Add Mode Specific Stuff #
        if "traj" in self.mode:
            self.controller.robot.reset_robot(randomize=False)

            self.timer.place(relx=0.79, rely=0.01)
            self.update_timer(time.time())

            traj_thread = threading.Thread(target=self.collect_trajectory)
            traj_thread.daemon = True
            traj_thread.start()

    def collect_trajectory(self):
        info = self.controller.info.copy()
        practice = self.mode == "practice_traj"
        self.controller.robot.collect_trajectory(info=info, practice=practice, reset_robot=False)
        self.end_trajectory()

    def update_timer(self, start_time):
        time_passed = time.time() - start_time
        zoom = self.controller.frames[EnlargedImagePage]
        page_inactive = self.controller.curr_frame not in [self, zoom]
        hide_timer = "traj" not in self.mode
        if page_inactive or hide_timer:
            return

        minutes_str = str(int(time_passed / 60))
        curr_seconds = int(time_passed) % 60

        if curr_seconds < 10:
            seconds_str = "0{0}".format(curr_seconds)
        else:
            seconds_str = str(curr_seconds)

        if not self.controller.robot.traj_running:
            start_time = time.time()

        self.time_str.set("{0}:{1}".format(minutes_str, seconds_str))
        self.controller.after(100, lambda: self.update_timer(start_time))

    def end_trajectory(self):
        save = self.controller.robot.traj_saved
        practice = self.mode == "practice_traj"

        # Update Based Off Success / Failure #
        if practice:
            pass
        elif save:
            self.controller.num_traj_saved += 1
        else:
            self.controller.frames[RequestedBehaviorPage].keep_last_task()

        # Check For Scene Changes #
        self.controller.show_frame(CanRobotResetPage)

    def set_home_frame(self, frame):
        self.home_frame = frame

    def set_mode(self, mode):
        self.mode = mode
        if self.mode == 'traj':
            self.capture_goal_btn.place_forget()
        else:
            self.capture_goal_btn.place(relx=0.45, rely=0.55)


    def edit_trajectory(self, save):
        if save:
            self.controller.robot.save_trajectory()
        else:
            self.controller.robot.delete_trajectory()
        self.controller.show_frame(RequestedBehaviorPage)
