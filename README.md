# 🐟 Fish Robot Controller

Oscillatory-gait controller for a biomimetic fish robot: a C++ core drives the
tail and fin on a Raspberry Pi, and a Python GUI edits the live configuration
and toggles logging over SSH.

**Components**:
- **C++ core** (`fish_control`) — reads `cfg.yaml`, drives the Dynamixel tail and RC-servo fin, logs data to CSV
- **Python GUI** (`fish_control_client.py`) — remote dashboard over SSH to edit `cfg.yaml` and toggle logging

**Author**: Gabriel Veigas Marques · **Master Project**: Biomimetic Fish Oscillatory Gait

---

## Repository Layout

```
fish-control/
│
├── cfg.yaml                      # Main config for both core & GUI
├── cpp/                          # C++ core source
│   ├── CMakeLists.txt
│   ├── src/
│   └── include/
├── fish_control/                 # Python GUI
│   ├── fish_control_client.py    #   remote dashboard
│   └── ui.py                     #   optional alternative GUI
├── logs/                         # CSV logs written by the C++ core
└── systemd/
    ├── fish.service              # runs the C++ core on boot
    └── fish-gui.service          # runs the Python dashboard
```

---

## Prerequisites

### On the Raspberry Pi

**C++ core**

| Dependency | Install |
|------------|---------|
| `g++`, `cmake`, `make` | `sudo apt install build-essential cmake` |
| `yaml-cpp` headers | `sudo apt install libyaml-cpp-dev` |
| Dynamixel SDK | installed via CMake (see below) |
| `pigpio` library & daemon | `sudo apt install pigpio` |

**Python GUI**

| Dependency | Install |
|------------|---------|
| Python 3 (3.7+) | preinstalled |
| `paramiko`, `pyyaml` | `pip install paramiko pyyaml` |
| `tkinter` | `sudo apt install python3-tk` |

---

## Build & Install

### 1. Install the Dynamixel SDK

```bash
cd ~/DynamixelSDK
mkdir build && cd build
cmake -DCMAKE_BUILD_TYPE=Release \
      -DBUILD_SHARED_LIBS=ON \
      -DCMAKE_INSTALL_PREFIX=/usr/local \
      ..
make -j4
sudo make install
sudo ldconfig
```

### 2. Build the C++ core

```bash
cd ~/projects/fish-control/cpp/build
cmake -DCMAKE_INSTALL_PREFIX=/usr/local ..
make -j4
sudo make install
```

This installs the `fish_control` binary into `/usr/local/bin/`.

### 3. Set up the Python GUI

```bash
# Create & activate the venv
cd ~/projects/fish-control
python3 -m venv venv-fish
source venv-fish/bin/activate

# Install Python deps
pip install paramiko pyyaml
sudo apt install python3-tk        # ensure tkinter is available
```

Run it manually with:

```bash
source venv-fish/bin/activate
python fish_control_client.py
```

---

## Systemd Services

Copy the unit files and enable them at boot:

```bash
sudo cp systemd/fish.service     /etc/systemd/system/
sudo cp systemd/fish-gui.service /etc/systemd/system/

sudo systemctl daemon-reload
sudo systemctl enable fish.service fish-gui.service
sudo systemctl start  fish.service fish-gui.service
```

| Service | Role |
|---------|------|
| `fish.service` | runs the C++ core on boot |
| `fish-gui.service` | runs the Python dashboard |

---

## Configuration

The config lives at `/home/fish_pizero/projects/fish-control/cfg.yaml` and is
shared by both the core and the GUI.

```yaml
mode: "symmetric_sin"         # "standby", "test", or "symmetric_sin"
amplitude_tail: 20.0
amplitude_fin:  20.0
frequency:      0.3
phase:          0.0
phi_tail:       0.0           # only in "test" mode
phi_fin:        0.0           # only in "test" mode
logging:        false         # true to start logging
```

| Field | Description |
|-------|-------------|
| `mode` | `"standby"`, `"test"`, or `"symmetric_sin"` |
| `amplitude_tail` | Tail oscillation amplitude |
| `amplitude_fin` | Fin oscillation amplitude |
| `frequency` | Oscillation frequency (Hz) |
| `phase` | Phase offset |
| `phi_tail` | Tail phase — only used in `"test"` mode |
| `phi_fin` | Fin phase — only used in `"test"` mode |
| `logging` | `true` to start logging |

---

## Quick Start

> The `fish.service` starts automatically on Pi boot. The steps below are for a
> manual start or after a reboot where the service is disabled.

```bash
# 1. Start pigpio
sudo systemctl enable pigpiod
sudo systemctl start  pigpiod

# 2. Launch services
sudo systemctl start fish.service
sudo systemctl start fish-gui.service

# 3. Open the GUI (locally or via SSH-X)
source ~/projects/fish-control/venv-fish/bin/activate
python fish_control_client.py
```

In the GUI:

1. Select **Host** → **Connect**.
2. **Load** reads the current `cfg.yaml`.
3. Modify fields and **Save**.
4. **Start/Stop Logging** toggles log streaming.

Logs appear in `projects/fish-control/logs/log_YYYYMMDD_HHMMSS.csv`.

The GUI ships with these preset hosts:

| Name | Address |
|------|---------|
| `EPFL` | `128.179.200.41` |
| `Local` | `fishpizero.local` |
| `EPFL2` | `128.179.204.90` |
| `Unknown` | `172.20.10.2` |

---

## After Code Changes

**C++ core**

```bash
cd ~/projects/fish-control/cpp/build
cmake ..
make -j4
sudo make install
sudo systemctl restart fish.service
```

**Python GUI**

```bash
sudo systemctl restart fish-gui.service
# or re-run: python fish_control_client.py
```

---

## GUI Source

The Python dashboard (`fish-gui.service`, run on a personal computer):

<details>
<summary><code>fish_control_client.py</code> — full source</summary>

```python
#!/usr/bin/env python3
import yaml
import paramiko
import tkinter as tk
from tkinter import messagebox, font, ttk
import traceback  # for full error dumps

# remote user + where the Pi's cfg.yaml lives
PI_USER    = "fish_pizero"
REMOTE_CFG = "/home/fish_pizero/projects/fish-control/cfg.yaml"

# name -> host-address
HOST_OPTIONS = {
    "EPFL":    "128.179.200.41",
    "Local":   "fishpizero.local",
    "EPFL2":   "128.179.204.90",
    "Unknown": "172.20.10.2",
}

class MacDashboard(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("🐟 Fish Remote Dashboard")
        self.resizable(False, False)

        # ── make a legible default font ──
        default_font = font.Font(family="Helvetica", size=11)
        self.option_add("*Font", default_font)

        # ── Host selector + Connect button + status ──
        ttk.Label(self, text="Host:")\
            .grid(row=0, column=0, sticky="w", padx=5, pady=5)
        self.host_combo = ttk.Combobox(
            self, values=list(HOST_OPTIONS.keys()), state="readonly", width=12
        )
        self.host_combo.set("EPFL")
        self.host_combo.grid(row=0, column=1, sticky="ew", padx=5)
        ttk.Button(self, text="Connect", command=self.on_connect)\
            .grid(row=0, column=2, padx=5)
        self.status_lbl = ttk.Label(self, text="Not connected", foreground="red")
        self.status_lbl.grid(row=0, column=3, padx=5)


        # ── Parameter fields ──
        self.fields = {}
        params = [
            ("mode",           ["standby","test","symmetric_sin"]),
            ("amplitude_tail", None),
            ("amplitude_fin",  None),
            ("frequency",      None),
            ("phase",          None),
            ("phi_tail",       None),
            ("phi_fin",        None),
        ]
        for i,(name,choices) in enumerate(params, start=1):
            label = name.replace("_"," ").title() + ":"
            ttk.Label(self, text=label)\
                .grid(row=i, column=0, sticky="e", padx=5, pady=2)
            var = tk.StringVar()
            self.fields[name] = var
            if choices:
                w = ttk.Combobox(self, textvariable=var, values=choices, state="readonly")
            else:
                w = ttk.Entry(self, textvariable=var)
            w.grid(row=i, column=1, columnspan=3, sticky="ew", padx=5, pady=2)

        # ── Load / Save buttons ──
        ttk.Button(self, text="Load from Pi", command=self.load_from_pi)\
            .grid(row=8, column=0, columnspan=2, pady=(15,5), padx=5, sticky="ew")
        ttk.Button(self, text="Save to Pi",  command=self.save_to_pi)\
            .grid(row=8, column=2, columnspan=2, pady=(15,5), padx=5, sticky="ew")

        # ── Single Start/Stop Logging toggle button ──
        self.log_btn = ttk.Button(self,
            text="Start Logging",
            command=self.toggle_logging
        )
        self.log_btn.grid(row=9, column=0, columnspan=4,
                          pady=(5,10), padx=5, sticky="ew")

        # ── Let columns stretch ──
        for c in range(4):
            self.columnconfigure(c, weight=1)

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
            self.status_lbl.config(text="Connected ✔️", foreground="green")
        except Exception as e:
            self.status_lbl.config(text=f"Error: {e}", foreground="red")

    def load_from_pi(self):
        try:
            ssh, sftp = self._ssh_sftp()
            with sftp.open(REMOTE_CFG, 'r') as f:
                cfg = yaml.safe_load(f)
            sftp.close(); ssh.close()

            # fill in all fields
            for name,var in self.fields.items():
                if name in cfg:
                    var.set(str(cfg[name]))
            # sync logging button
            current = cfg.get("logging", False)
            self.log_btn.config(text="Stop Logging" if current else "Start Logging")

            self.status_lbl.config(text="Loaded ✔️", foreground="green")
        except Exception as e:
            traceback.print_exc()
            self.status_lbl.config(text=f"Error: {e}", foreground="red")

    def save_to_pi(self):
        try:
            # first read existing config to preserve logging flag
            ssh, sftp = self._ssh_sftp()
            with sftp.open(REMOTE_CFG, 'r') as f:
                old_cfg = yaml.safe_load(f)

            # build new config from UI fields
            new_cfg = {
                name: (var.get() if name=="mode" else float(var.get()))
                for name,var in self.fields.items()
            }
            # preserve logging state
            new_cfg["logging"] = old_cfg.get("logging", False)
            # write directly to the config file
            with sftp.open(REMOTE_CFG, 'w') as f:
                f.write(yaml.safe_dump(new_cfg))
            sftp.close(); ssh.close()

            messagebox.showinfo("Saved", "Configuration written to Pi.")
            self.status_lbl.config(text="Saved ✔️", foreground="green")
        except Exception as e:
            traceback.print_exc()
            self.status_lbl.config(text=f"Error: {e}", foreground="red")

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
            self.log_btn.config(text="Stop Logging" if new_state else "Start Logging")
            self.status_lbl.config(
                text=("Logging On ✔️" if new_state else "Logging Off ✔️"),
                foreground="green"
            )
        except Exception as e:
            traceback.print_exc()
            self.status_lbl.config(text=f"Error: {e}", foreground="red")


if __name__ == "__main__":
    app = MacDashboard()
    app.mainloop()
```

</details>

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| **Port errors** | Check `/dev/ttyUSB0` and permissions: `sudo usermod -aG dialout $USER` |
| **Dynamixel ping fail** | Ensure the U2D2 green LED is on and wiring is correct |
| **GUI blank** | Confirm tkinter in the venv: `python -c "import tkinter; tkinter._test()"` |
| **Logging not toggling** | Verify the `logging:` field exists in `cfg.yaml` |

---

Happy fish-driving! 🐟
