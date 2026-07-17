#!/usr/bin/env python3
import yaml
import paramiko
import tkinter as tk
from tkinter import messagebox, font, ttk
 # ── Dark‑mode widgets ──
import customtkinter as ctk
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")   # accent colour
import traceback  # for full error dumps
import matplotlib
matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
import numpy as np

# remote user + where the Pi's cfg.yaml
PI_USER    = "fish_pizero"
REMOTE_CFG = "/home/fish_pizero/fish-control/cfg.yaml"

# name -> host-address
HOST_OPTIONS = {
    "Pi (hotspot)": "172.20.10.13",
    "EPFL":    "128.179.200.41",
    "GabsPhone":   "fishpizero.local",
    "EPFL2":   "128.179.204.90",
    "Unknown": "172.20.10.2",
    "CREATE Lab": "128.179.130.218"
}

class MacDashboard(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("🐟 Fish Remote Dashboard")
        # allow the user to enlarge/shrink the window
        self.resizable(True, True)
        # give a roomier default size (WxH in pixels)
        self.geometry("1200x800")
        # arrange three root columns:
        # 0 & 1  = controls (fixed width)
        # 2      = visualisations (expands)

        # build two main areas: left = controls, right = visualisations
        self.ctrl = ctk.CTkFrame(self, fg_color="transparent")
        self.ctrl.grid(row=0, column=0, sticky="nw", padx=10, pady=5)
        self.vis  = ctk.CTkFrame(self, fg_color="transparent")
        self.vis.grid(row=0, column=1, sticky="nsew", padx=10, pady=5)

        # visual column expands with window
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        # ── make a legible default font ──
        default_font = font.Font(family="Helvetica", size=11)
        self.option_add("*Font", default_font)
        bold_font = ctk.CTkFont(family="Helvetica", size=14, weight="bold")

        style = ttk.Style(self)
        try:
            style.theme_use("clam")   # more neutral than Aqua defaults
        except:
            pass
        style.configure("TButton", padding=6)
        # style.configure("TLabel", background="#f0f0f0")
        # self.configure(background="#f0f0f0")
        # self.ctrl.configure(style="TFrame")
        # self.vis.configure(style="TFrame")

        # --- Headline -------------------------------------------------
        title_font = ctk.CTkFont(family="Helvetica", size=28, weight="bold")
        ctk.CTkLabel(self.ctrl, text="🕹️ Fish Controller 🐟", font=title_font,)\
            .grid(row=0, column=0, columnspan=3, pady=(0, 15))

        # ── Host selector + Connect button + status ──
        ctk.CTkLabel(self.ctrl, text="Host:", font=bold_font)\
            .grid(row=1, column=0, sticky="w", padx=5, pady=(5, 15))
        self.host_combo = ctk.CTkOptionMenu(
            self.ctrl, values=list(HOST_OPTIONS.keys())
        )
        self.host_combo.set("EPFL")
        self.host_combo.grid(row=1, column=1, sticky="ew", padx=5, pady=(5, 15))
        ctk.CTkButton(self.ctrl, text="Connect", command=self.on_connect)\
            .grid(row=1, column=2, padx=5, pady=(5, 15))


        # --- Mode selection segmented button (no content area) ---
        self.fields = {}
        self.widgets = {}
        self.labels  = {}
        self.mode_var = tk.StringVar(value="standby")
        self.mode_selector = ctk.CTkSegmentedButton(
            self.ctrl,
            values=["standby", "gliding_turn", "symmetric_sin", "power_turn", "ratchet_turn"],
            variable=self.mode_var,
            command=lambda v: self.fields["mode"].set(v)
        )
        self.mode_selector.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(0, 10))
        self.fields["mode"] = self.mode_var

        # --- Parameter frames for each mode (no duplicate tab bar) ----------
        self.param_container = ctk.CTkFrame(self.ctrl, fg_color="transparent")
        self.param_container.grid(row=3, column=0, columnspan=3,
                                  sticky="nsew", pady=(0, 10))
        self.param_container.rowconfigure(0, weight=1)
        self.param_container.columnconfigure(0, weight=1)

        # One stacked frame per mode
        frame_standby = ctk.CTkFrame(self.param_container, fg_color="transparent")
        frame_sym     = ctk.CTkFrame(self.param_container, fg_color="transparent")
        frame_glide   = ctk.CTkFrame(self.param_container, fg_color="transparent")
        frame_power   = ctk.CTkFrame(self.param_container, fg_color="transparent")
        frame_ratchet = ctk.CTkFrame(self.param_container, fg_color="transparent")
        for f in (frame_standby, frame_sym, frame_glide, frame_power, frame_ratchet):
            f.grid(row=0, column=0, sticky="nsew")

        # Helper for sliders
        slider_cfg = dict(progress_color="#00BFFF", fg_color="#444444")
        def make_slider(parent, var, frm, to, steps, fmt):
            s = ctk.CTkSlider(parent, from_=frm, to=to, number_of_steps=steps,
                              command=lambda val, v=var: v.set(fmt.format(val)))
            s.configure(**slider_cfg)
            s.set(0)
            return s

        # Parameter lists per mode
        mode_params = {
            "symmetric_sin": ["amplitude_tail", "amplitude_fin",
                              "frequency", "phase"],
            "gliding_turn":  ["phi_tail", "phi_fin"],
            "power_turn":    ["amplitude_tail", "frequency", "phi_tail", "phi_fin"],
            "ratchet_turn":  ["amplitude_tail", "frequency", "cycles", "phi_fin"],
        }

        frame_for_mode = {
            "standby":       frame_standby,
            "symmetric_sin": frame_sym,
            "gliding_turn":  frame_glide,
            "power_turn":    frame_power,
            "ratchet_turn":  frame_ratchet,
        }

        # Build widgets for each active‑input mode
        frame_rows = {k: 0 for k in frame_for_mode if k != "standby"}
        for mode, params in mode_params.items():
            parent = frame_for_mode[mode]
            for name in params:
                var = self.fields.get(name)
                if var is None:
                    var = tk.StringVar(value="0")
                    self.fields[name] = var

                if name.endswith("amplitude"):
                    w = make_slider(parent, var, 0, 90, 18, "{:.0f}")
                elif name.endswith("frequency"):
                    w = make_slider(parent, var, 0, 3, 60, "{:.2f}")
                elif name == "phase":
                    w = make_slider(parent, var, -180, 180, 360, "{:.0f}")
                elif name == "cycles":
                    w = make_slider(parent, var, 1, 10, 9, "{:.0f}")
                elif name == "phi_fin":
                    w = ctk.CTkEntry(parent, textvariable=var)
                else:  # phi_tail
                    w = ctk.CTkEntry(parent, textvariable=var)

                row = frame_rows[mode]
                lbl = name.replace("_", " ").title() + ":"
                ctk.CTkLabel(parent, text=lbl, font=bold_font)\
                    .grid(row=row, column=0, sticky="w", padx=5, pady=4)
                w.grid(row=row, column=1, sticky="ew", padx=5, pady=4)
                if isinstance(w, ctk.CTkSlider):
                    ctk.CTkLabel(parent, textvariable=var, width=40)\
                        .grid(row=row, column=2, sticky="w")
                parent.columnconfigure(1, weight=1)
                self.widgets[name] = w
                frame_rows[mode] += 1
                if name in ("amplitude_tail","amplitude_fin","frequency","phase"):
                    var.trace_add("write", lambda *args, self=self: self.update_plot())

        # Read‑only display in STANDBY
        readonly_params = ["amplitude_tail", "amplitude_fin",
                           "frequency", "phase",
                           "phi_tail", "phi_fin",
                           "cycles"]
        for r, name in enumerate(readonly_params):
            var = self.fields.get(name)
            if var is None:
                var = tk.StringVar(value="0")
                self.fields[name] = var
            lbl = name.replace("_", " ").title() + ":"
            ctk.CTkLabel(frame_standby, text=lbl, font=bold_font)\
                .grid(row=r, column=0, sticky="w", padx=5, pady=2)
            ctk.CTkLabel(frame_standby, textvariable=var, width=80, anchor="e")\
                .grid(row=r, column=1, sticky="e", padx=5, pady=2)
        frame_standby.columnconfigure(1, weight=1)

        # Raise the correct frame when mode changes
        def _raise_frame(*_):
            mode = self.fields["mode"].get()
            frame_for_mode.get(mode, frame_standby).tkraise()
        self.fields["mode"].trace_add("write", _raise_frame)
        _raise_frame()

        # centred button frame for Get / Send
        btn_frame = ctk.CTkFrame(self.ctrl, fg_color="transparent")
        btn_frame.grid(row=6, column=0, columnspan=3, pady=(10,0))
        btn_font = ctk.CTkFont(family="Helvetica", size=14, weight="bold")
        get_btn  = ctk.CTkButton(
            btn_frame,
            text="Get current parameters",
            command=self.load_from_pi,
            width=160,
            height=50,
            font=btn_font
        )
        send_btn = ctk.CTkButton(
            btn_frame,
            text="Send new parameters",
            command=self.save_to_pi,
            width=160,
            height=50,
            font=btn_font
        )
        get_btn.pack(side="left", padx=10)
        send_btn.pack(side="left", padx=10)

        # ── Plot area ──
        self.plot_frame = ctk.CTkFrame(self.vis, fg_color="transparent")
        # move to the right‑hand column
        self.plot_frame.grid(row=0, column=0, padx=5, pady=5, sticky="nsew")
        self.fig, self.ax = plt.subplots(figsize=(4, 3))
        self.ax.set_facecolor("#222222")
        self.fig.patch.set_facecolor("#222222")
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.plot_frame)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)
        self.update_plot()

        # ── Kinematic animation ──
        self.anim_frame = ctk.CTkFrame(self.vis, fg_color="transparent")
        self.anim_frame.grid(row=1, column=0,
                             padx=0, pady=0, sticky="nsew")

        self.fig_anim, self.ax_anim = plt.subplots(figsize=(4, 3))
        self.fig_anim.patch.set_facecolor("#222222")
        self.ax_anim.set_facecolor("#222222")
        for spine in self.ax_anim.spines.values():
            spine.set_visible(False)
        self.canvas_anim = FigureCanvasTkAgg(self.fig_anim, master=self.anim_frame)
        self.canvas_anim.get_tk_widget().grid(row=0, column=0, sticky="nsew")

        # allow the canvas to expand with the frame
        self.anim_frame.rowconfigure(0, weight=1)
        self.anim_frame.columnconfigure(0, weight=1)

        # two line objects that will be updated every frame
        self.tail_seg, = self.ax_anim.plot([], [], 'o-', lw=6, markersize=12,
                                           label="Tail", color="#00BFFF")
        self.fin_seg,  = self.ax_anim.plot([], [], 'o-', lw=6, markersize=12,
                                           label="Fin", color="#FFA500")

        self.ax_anim.set_aspect("equal", adjustable="box")
        # expand limits so the enlarged bars fit fully in view
        total_len = 4.8          # L1 + L2 (3.0 + 1.8)
        self.ax_anim.set_xlim(-total_len, total_len * 0.3)
        self.ax_anim.set_ylim(-total_len * 0.3, total_len * 0.7)
        self.ax_anim.axis("off")

        # keep a reference so the animation is not garbage‑collected
        self.anim = FuncAnimation(
            self.fig_anim,
            self._anim_update,
            init_func=self._anim_init,
            frames=200,        # ~4 s at 50 fps; then repeats
            interval=30,       # 33 ms per frame ≈ 30 fps
            blit=True,
            repeat=True
        )

        # after anim frame creation
        self.vis.rowconfigure(0, weight=1)
        self.vis.rowconfigure(1, weight=1)
        self.vis.columnconfigure(0, weight=1)

        # ── Single Start/Stop Logging toggle button ──
        log_btn_font = ctk.CTkFont(family="Helvetica", size=16, weight="bold")
        self.log_btn = ctk.CTkButton(
            self.ctrl,
            text="Start Logging ▶️",
            command=self.toggle_logging,
            font=log_btn_font,
            height=50,
        )
        self.log_btn.grid(row=10, column=0, columnspan=3,
                  pady=(10,0), padx=5, sticky="ew")
        # ── Big red STOP button ──
        self.stop_btn = ctk.CTkButton(
            self.ctrl,
            text="STOP",
            command=self.stop_to_standby,
            fg_color="#FF3030",        # vibrant red for dark mode
            hover_color="#FF5050",
            text_color="white",
            font=("Helvetica", 16, "bold")
        )
        self.stop_btn.grid(row=12, column=0, columnspan=3,
                    pady=(10, 10), padx=5, sticky="ew")
        self.stop_btn.configure(height=60)

        # controls columns fixed; let the visual column (2) expand
        self.rowconfigure(10, weight=1)   # sine‑wave plot
        self.rowconfigure(11, weight=1)   # kinematic animation

        # ── Status box ──
        self.status_frame = ctk.CTkFrame(self.ctrl, fg_color="#2A2A2A", border_color="#696969",border_width=1)
        self.status_frame.grid(row=13, column=0, columnspan=3, padx=5, pady=(0,10), sticky="ew")
        self.status_frame.columnconfigure(0, weight=1)

        status_font_big = ctk.CTkFont(family="Helvetica", size=24, weight="bold")
        status_font_small = ctk.CTkFont(family="Helvetica", size=18, weight="bold")

        self.conn_status  = ctk.CTkLabel(self.status_frame, text="Not connected",
                                         text_color="#FF3030", font=status_font_big)
        self.conn_status.grid(row=0, column=0, pady=(10,0))

        self.log_status = ctk.CTkLabel(self.status_frame, text="Logging Off ⏸️",
                                       text_color="#FF3030", font=status_font_small)
        self.log_status.grid(row=1, column=0, pady=(10,0))

        self.action_status = ctk.CTkLabel(self.status_frame, text="", font=status_font_small)
        self.action_status.grid(row=2, column=0, pady=(10,10))

    def _ssh_sftp(self):
        """Return an (ssh, sftp) pair connected to the selected host."""
        host_key = self.host_combo.get()
        if host_key not in HOST_OPTIONS:
            raise RuntimeError(f"Unknown host “{host_key}”")
        ssh = paramiko.SSHClient()
        ssh.load_system_host_keys()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(HOST_OPTIONS[host_key], username=PI_USER, timeout=5)
        return ssh, ssh.open_sftp()

    def on_connect(self):
        try:
            ssh, sftp = self._ssh_sftp()
            sftp.close(); ssh.close()
            self.conn_status.configure(text="SSH Connected", text_color="#00FF00")
        except Exception as e:
            self.conn_status.configure(text="SSH Not connected", text_color="#FF3030")
            self.action_status.configure(text=f"Error: {e}")

    def load_from_pi(self):
        try:
            ssh, sftp = self._ssh_sftp()
            with sftp.open(REMOTE_CFG, 'r') as f:
                cfg = yaml.safe_load(f)
                if cfg is None:
                    cfg = {}
            sftp.close(); ssh.close()

            # fill in all fields
            for name,var in self.fields.items():
                if cfg is None:
                    print("Warning: config is None, skipping load_from_pi")
                    return
                if name in cfg:
                    var.set(str(cfg[name]))
            # sync logging button
            current = cfg.get("logging", False)
            self.log_btn.configure(
                text=("Stop Logging ⏯️" if current else "Start Logging ▶️")
            )
            self.log_status.configure(
                text=("Logging ✅" if current else "Logging ❌"),
                text_color="#00FF00" if current else "#FF3030"
            )

            self._flash_action("Parameters Loaded", "#00FF00")
        except Exception as e:
            traceback.print_exc()
            self._flash_action(f"Error: {e}", "#FF3030")

    def save_to_pi(self):
        try:
            # first read existing config to preserve logging flag
            ssh, sftp = self._ssh_sftp()
            with sftp.open(REMOTE_CFG, 'r') as f:
                old_cfg = yaml.safe_load(f) or {}

            # build new config from UI fields
            new_cfg = {}
            for name, var in self.fields.items():
                val = var.get().strip()
                if name == "mode":
                    new_cfg[name] = val or old_cfg.get(name)
                else:
                    if val == "":
                        new_cfg[name] = old_cfg.get(name)
                    else:
                        try:
                            new_cfg[name] = float(val)
                        except ValueError:
                            new_cfg[name] = old_cfg.get(name)
            # preserve logging state
            new_cfg["logging"] = old_cfg.get("logging", False)
            # write directly to the config file
            with sftp.open(REMOTE_CFG, 'w') as f:
                f.write(yaml.safe_dump(new_cfg))
            sftp.close(); ssh.close()

            self._flash_action("Parameters Sent ✔️", "#00FF00")
        except Exception as e:
            traceback.print_exc()
            self._flash_action(f"Error: {e}", "#FF3030")

    def toggle_logging(self):
        """Toggle remote logging on/off and update button text."""
        try:
            ssh, sftp = self._ssh_sftp()
            # read current
            with sftp.open(REMOTE_CFG, 'r') as f:
                cfg = yaml.safe_load(f)
            new_state = not cfg.get("logging", False)
            cfg["logging"] = new_state
            # write logging flag directly
            with sftp.open(REMOTE_CFG, 'w') as f:
                f.write(yaml.safe_dump(cfg))
            sftp.close(); ssh.close()

            # update UI
            self.log_btn.configure(
                text=("Stop Logging ⏯️" if new_state else "Start Logging ▶️")
            )
            self.log_status.configure(
                text=("Logging On ▶️" if new_state else "Logging Off ⏸️"),
                text_color="#00FF00" if new_state else "#FF3030"
            )
        except Exception as e:
            traceback.print_exc()
            self._flash_action(f"Error: {e}", "#FF3030")

    # ------------------------------------------------------------------
    # UI helpers
    # ------------------------------------------------------------------
    def stop_to_standby(self):
        """Put robot into STANDBY mode immediately."""
        self.fields["mode"].set("standby")
        # Save updated mode to Pi right away
        try:
            self.save_to_pi()
        except Exception as e:
            traceback.print_exc()
            self._flash_action(f"Error: {e}", "#FF3030")

    # ------------------------------------------------------------------
    # Helper to show transient action status with fading color effect
    # ------------------------------------------------------------------
    def _flash_action(self, text: str, color: str = "#00FF00",
                      duration_ms: int = 10000, steps: int = 50):
        """
        Show `text` in `color` and linearly fade that colour to grey (#AAAAAA)
        over `duration_ms` milliseconds using `steps` increments.
        """
        # cancel previous fade if one is scheduled
        if hasattr(self, "_action_after_id"):
            try:
                self.after_cancel(self._action_after_id)
            except Exception:
                pass

        # helper: convert "#RRGGBB" to tuple of ints
        def _hex_to_rgb(h: str):
            h = h.lstrip("#")
            return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

        start_rgb = _hex_to_rgb(color)
        end_rgb   = _hex_to_rgb("AAAAAA")
        interval  = max(1, duration_ms // steps)

        self.action_status.configure(text=text)

        def _step(i: int = 0):
            t = i / steps  # 0‒1
            rgb = tuple(int(s + (e - s) * t) for s, e in zip(start_rgb, end_rgb))
            self.action_status.configure(text_color=f"#{rgb[0]:02X}{rgb[1]:02X}{rgb[2]:02X}")
            if i < steps:
                self._action_after_id = self.after(interval, lambda: _step(i + 1))
            else:
                # ensure final colour is exactly grey
                self.action_status.configure(text_color="#AAAAAA")

        _step(0)

    def update_plot(self):
        """Redraw the tail and fin sine waves for two cycles."""
        try:
            A_t = float(self.fields["amplitude_tail"].get())
            A_f = float(self.fields["amplitude_fin"].get())
            f   = float(self.fields["frequency"].get())
            ph  = float(self.fields["phase"].get())
        except Exception:
            return
        if f == 0:
            f = 1e-6    # tiny value to avoid divide-by-zero
        t = np.linspace(0, 2/f, 400)
        ph_rad = np.radians(ph)  # convert phase to radians
        tail = A_t * np.sin(2*np.pi*f*t)
        fin  = A_f * np.sin(2*np.pi*f*t + ph_rad)
        self.ax.clear()

        # dark background and no spines/ticks
        self.ax.set_facecolor("#222222")
        for spine in self.ax.spines.values():
            spine.set_visible(False)
        # Show axis labels and grid, but keep dark style
        self.ax.tick_params(left=True, bottom=True, labelleft=True, labelbottom=True, colors="white")
        self.ax.xaxis.label.set_color("white")
        self.ax.yaxis.label.set_color("white")
        self.ax.plot(t, tail, label="Tail", color="#00BFFF")  # DeepSkyBlue
        self.ax.plot(t, fin,  label="Fin",  color="#FFA500")  # Orange
        self.ax.set_xlim(0, 2/f)
        self.ax.set_xlabel("Time (s)")
        self.ax.set_ylabel("Angle")
        self.ax.grid(True, color="#444444", linewidth=0.5)
        legend = self.ax.legend(loc="upper right")
        legend.get_frame().set_facecolor("#222222")
        legend.get_frame().set_edgecolor("none")
        for text in legend.get_texts():
            text.set_color("white")
        self.fig.tight_layout()
        self.canvas.draw()

        # also refresh the stick‑figure if it exists
        if hasattr(self, "canvas_anim"):
            self.canvas_anim.draw_idle()

    # ------------------------------------------------------------------
    # Animation helpers
    # ------------------------------------------------------------------
    def _anim_init(self):
        """Initial draw – empty segments."""
        self.tail_seg.set_data([], [])
        self.fin_seg.set_data([], [])
        return self.tail_seg, self.fin_seg

    def _anim_update(self, frame):
        """Render one animation frame."""
        try:
            A_t = float(self.fields["amplitude_tail"].get())  # degrees
            A_f = float(self.fields["amplitude_fin"].get())   # degrees
            f   = float(self.fields["frequency"].get())       # Hz
            ph  = float(self.fields["phase"].get())           # radians
        except Exception:
            # parameters incomplete – just keep current drawing
            return self.tail_seg, self.fin_seg

        # bar lengths (arbitrary units)
        L1, L2 = 2.5, 1.5
        # shift the whole drawing so it sits roughly mid‑canvas
        OFFSET_X = 1.0   # positive → right
        OFFSET_Y = 1.0   # positive → up

        # map frame index to physical time
        t = frame / 50.0

        ph_rad = np.radians(ph)

        # instantaneous angles
        tail_ang = np.radians(A_t) * np.sin(2 * np.pi * f * t)
        fin_ang  = np.radians(A_f) * np.sin(2 * np.pi * f * t + ph_rad)

        # forward kinematics
        x0, y0 = 0.0, 0.0
        x1 = -L1 * np.cos(tail_ang)                       # mirrored
        y1 = L1 * np.sin(tail_ang)
        x2 = x1 - L2 * np.cos(tail_ang + fin_ang)         # mirrored
        y2 = y1 + L2 * np.sin(tail_ang + fin_ang)

        # update the two line segments with translation
        self.tail_seg.set_data([x0 + OFFSET_X, x1 + OFFSET_X],
                               [y0 + OFFSET_Y, y1 + OFFSET_Y])
        self.fin_seg.set_data([x1 + OFFSET_X, x2 + OFFSET_X],
                               [y1 + OFFSET_Y, y2 + OFFSET_Y])
        return self.tail_seg, self.fin_seg

    # update_visibility method removed (obsolete)


if __name__ == "__main__":
    app = MacDashboard()
    app.mainloop()