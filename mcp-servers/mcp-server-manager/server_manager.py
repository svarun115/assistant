"""
MCP Server Manager - GUI application for managing MCP servers
"""

import tkinter as tk
from tkinter import ttk, messagebox
import subprocess
import threading
import json
import os
import sys
import queue
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime

# Configuration
BASE_DIR = Path(__file__).parent.parent
CONFIG_FILE = Path(__file__).parent / "servers.json"


class ToolTip:
    """Dynamic tooltip that updates on hover"""

    def __init__(self, widget, text_func):
        self.widget = widget
        self.text_func = text_func
        self.tooltip = None
        widget.bind("<Enter>", self.show)
        widget.bind("<Leave>", self.hide)

    def show(self, event=None):
        text = self.text_func()
        if not text:
            return

        x, y, _, _ = self.widget.bbox("insert") if hasattr(self.widget, 'bbox') else (0, 0, 0, 0)
        x += self.widget.winfo_rootx() + 25
        y += self.widget.winfo_rooty() + 25

        self.tooltip = tk.Toplevel(self.widget)
        self.tooltip.wm_overrideredirect(True)
        self.tooltip.wm_geometry(f"+{x}+{y}")

        label = ttk.Label(self.tooltip, text=text, background="#333", foreground="#fff",
                          relief="solid", borderwidth=1, padding=(8, 4),
                          font=('Consolas', 9))
        label.pack()

    def hide(self, event=None):
        if self.tooltip:
            self.tooltip.destroy()
            self.tooltip = None


class ServerProcess:
    """Manages a single server process"""

    def __init__(self, server_config, base_dir):
        self.config = server_config
        self.base_dir = base_dir
        self.process = None
        self.output_queue = queue.Queue()
        self.reader_thread = None
        self.tool_call_count = 0
        self.tool_calls_by_name = {}  # {tool_name: count}
        self.last_tool_called = None
        # Mode support: servers with "modes" field can switch between e.g. prod/dev
        self.current_mode = self.config.get('default_mode')

    @property
    def has_modes(self):
        return 'modes' in self.config and self.config['modes']

    @property
    def mode_names(self):
        if not self.has_modes:
            return []
        return list(self.config['modes'].keys())

    def get_mode_label(self, mode_key):
        if not self.has_modes:
            return mode_key
        return self.config['modes'].get(mode_key, {}).get('label', mode_key)

    def get_effective_env(self):
        """Get env dict with mode-specific overrides merged in."""
        env = dict(self.config.get('env', {}))
        if self.has_modes and self.current_mode:
            mode_env = self.config['modes'].get(self.current_mode, {}).get('env', {})
            env.update(mode_env)
        return env

    @property
    def id(self):
        return self.config['id']

    @property
    def name(self):
        return self.config['name']

    @property
    def port(self):
        return self.config['port']

    @property
    def directory(self):
        return self.base_dir / self.config['directory']

    def is_running(self):
        """Check if process is running"""
        if self.process and self.process.poll() is None:
            return True
        return False

    def check_health(self):
        """Check if server responds to health check (cached result)"""
        return getattr(self, '_health_status', False)

    def _do_health_check(self):
        """Perform actual health check in background"""
        try:
            url = f"http://localhost:{self.port}/healthz"
            req = urllib.request.Request(url, method='GET')
            with urllib.request.urlopen(req, timeout=1) as response:
                self._health_status = response.status == 200
        except:
            self._health_status = False

    def get_pid_using_port(self):
        """Find PID of process using this server's port"""
        try:
            result = subprocess.run(
                ['netstat', '-ano', '-p', 'TCP'],
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
            )
            for line in result.stdout.split('\n'):
                if f':{self.port}' in line and 'LISTENING' in line:
                    parts = line.split()
                    if parts:
                        return int(parts[-1])
        except:
            pass
        return None

    def kill_process_on_port(self):
        """Kill any process using this server's port"""
        pid = self.get_pid_using_port()
        if pid:
            try:
                subprocess.run(
                    ['taskkill', '/F', '/PID', str(pid)],
                    capture_output=True,
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
                )
                # Wait a moment for port to be released
                import time
                time.sleep(0.5)
                return True, f"Killed existing process (PID {pid})"
            except Exception as e:
                return False, f"Failed to kill PID {pid}: {e}"
        return True, "Port was free"

    def start(self):
        """Start the server process"""
        if self.is_running():
            return False, "Already running"

        # Kill any existing process on the port
        pid_on_port = self.get_pid_using_port()
        port_msg = ""
        if pid_on_port:
            kill_success, kill_msg = self.kill_process_on_port()
            if not kill_success:
                return False, kill_msg
            port_msg = f" (killed existing PID {pid_on_port})"

        # Build command
        cmd = self.config['command']
        env = os.environ.copy()
        env.update(self.get_effective_env())

        # Handle venv activation for Python servers
        if self.config.get('venv') and self.config['type'] == 'python':
            venv_activate = self.directory / 'venv' / 'Scripts' / 'activate.bat'
            if venv_activate.exists():
                cmd = f'call "{venv_activate}" && {cmd}'

        try:
            # Start process
            self.process = subprocess.Popen(
                cmd,
                cwd=str(self.directory),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.PIPE,
                shell=True,
                bufsize=1,
                universal_newlines=True,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
            )

            # Start output reader thread
            self.reader_thread = threading.Thread(target=self._read_output, daemon=True)
            self.reader_thread.start()

            return True, f"Started on port {self.port}{port_msg}"
        except Exception as e:
            return False, str(e)

    def stop(self):
        """Stop the server process"""
        if not self.is_running():
            return False, "Not running"

        try:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
            self.process = None
            return True, "Stopped"
        except Exception as e:
            return False, str(e)

    def restart(self):
        """Restart the server process"""
        self.stop()
        return self.start()

    def _read_output(self):
        """Read process output in background thread"""
        import re
        # Primary pattern: [TOOL_CALL] tool_name
        tool_call_pattern = re.compile(r'\[TOOL_CALL\]\s+(\S+)')

        try:
            for line in self.process.stdout:
                self.output_queue.put(line)

                # Detect tool calls
                match = tool_call_pattern.search(line)
                if match:
                    tool_name = match.group(1)
                    self.tool_call_count += 1
                    self.last_tool_called = tool_name
                    self.tool_calls_by_name[tool_name] = self.tool_calls_by_name.get(tool_name, 0) + 1
        except:
            pass

    def reset_stats(self):
        """Reset tool call statistics"""
        self.tool_call_count = 0
        self.tool_calls_by_name = {}
        self.last_tool_called = None

    def get_tool_breakdown(self):
        """Get formatted string of tool call breakdown"""
        if not self.tool_calls_by_name:
            return "No tool calls yet"

        sorted_tools = sorted(self.tool_calls_by_name.items(), key=lambda x: -x[1])
        lines = [f"{name}: {count}" for name, count in sorted_tools]
        return "\n".join(lines)

    def get_output(self):
        """Get pending output from queue"""
        lines = []
        while not self.output_queue.empty():
            try:
                lines.append(self.output_queue.get_nowait())
            except queue.Empty:
                break
        return ''.join(lines)


class ServerManagerGUI:
    """Main GUI application"""

    def __init__(self, root):
        self.root = root
        self.root.title("MCP Server Manager")
        self.root.geometry("1000x700")
        self.root.minsize(800, 500)

        # Load configuration
        self.load_config()

        # Initialize server processes
        self.servers = {}
        for server_config in self.config['servers']:
            server = ServerProcess(server_config, BASE_DIR)
            self.servers[server.id] = server

        # Build UI
        self.setup_ui()

        # Start status update loop
        self.update_status()
        self.update_consoles()

    def load_config(self):
        """Load server configuration from JSON"""
        with open(CONFIG_FILE, 'r') as f:
            self.config = json.load(f)

    def setup_ui(self):
        """Build the user interface"""
        # Configure grid
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_rowconfigure(1, weight=1)

        # Top frame - server controls
        self.setup_control_frame()

        # Bottom frame - console outputs
        self.setup_console_frame()

        # Status bar
        self.setup_status_bar()

    def setup_control_frame(self):
        """Setup the server control panel"""
        # Top container for servers and groups side by side
        top_container = ttk.Frame(self.root)
        top_container.grid(row=0, column=0, sticky="nsew", padx=10, pady=5)
        top_container.grid_columnconfigure(0, weight=1)

        # Server list frame
        control_frame = ttk.LabelFrame(top_container, text="Servers", padding=10)
        control_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        control_frame.grid_columnconfigure(1, weight=1)

        # Server rows
        self.status_labels = {}
        self.status_indicators = {}
        self.call_count_labels = {}
        self.port_vars = {}   # Editable port fields per server
        self.mode_vars = {}   # Mode dropdown vars for servers with modes

        for i, server in enumerate(self.servers.values()):
            # Status indicator (colored dot)
            indicator = tk.Canvas(control_frame, width=16, height=16, highlightthickness=0, bg='#dcdad5')
            indicator.grid(row=i, column=0, padx=(0, 5), pady=3)
            indicator.create_oval(2, 2, 14, 14, fill='gray', outline='darkgray', tags='status')
            self.status_indicators[server.id] = indicator

            # Server name and description
            name_frame = ttk.Frame(control_frame)
            name_frame.grid(row=i, column=1, sticky="w", padx=5, pady=3)

            name_label = ttk.Label(name_frame, text=server.name, font=('Segoe UI', 10, 'bold'))
            name_label.pack(anchor='w')

            desc_label = ttk.Label(name_frame, text=server.config['description'],
                                   font=('Segoe UI', 8), foreground='gray')
            desc_label.pack(anchor='w')

            # Port + Mode controls in one frame
            config_frame = ttk.Frame(control_frame)
            config_frame.grid(row=i, column=2, padx=5, pady=3)

            # Editable port field
            port_var = tk.StringVar(value=str(server.port))
            self.port_vars[server.id] = port_var
            ttk.Label(config_frame, text=":", font=('Consolas', 9)).pack(side='left')
            port_entry = ttk.Entry(config_frame, textvariable=port_var, width=6,
                                   font=('Consolas', 9), justify='center')
            port_entry.pack(side='left')

            # Mode dropdown (only for servers with modes, e.g. journal-db)
            if server.has_modes:
                mode_var = tk.StringVar(value=server.current_mode or server.mode_names[0])
                self.mode_vars[server.id] = mode_var
                mode_labels = {k: server.get_mode_label(k) for k in server.mode_names}
                mode_combo = ttk.Combobox(config_frame, textvariable=mode_var, width=12,
                                          values=list(mode_labels.values()),
                                          state='readonly', font=('Segoe UI', 8))
                mode_combo.pack(side='left', padx=(5, 0))
                # Map display label back to mode key on selection
                def on_mode_change(event, sid=server.id, labels=mode_labels, var=mode_var):
                    selected_label = var.get()
                    for key, label in labels.items():
                        if label == selected_label:
                            self.servers[sid].current_mode = key
                            break
                mode_combo.bind('<<ComboboxSelected>>', on_mode_change)
                # Set initial display label
                mode_combo.set(server.get_mode_label(server.current_mode))

            # Status text
            status_label = ttk.Label(control_frame, text="Stopped", width=10)
            status_label.grid(row=i, column=3, padx=10, pady=3)
            self.status_labels[server.id] = status_label

            # Tool call count (with tooltip showing breakdown)
            call_count_label = ttk.Label(control_frame, text="0 calls", width=10, foreground='#6b7280', cursor='hand2')
            call_count_label.grid(row=i, column=4, padx=5, pady=3)
            self.call_count_labels[server.id] = call_count_label
            ToolTip(call_count_label, lambda s=server: s.get_tool_breakdown())

            # Control buttons
            btn_frame = ttk.Frame(control_frame)
            btn_frame.grid(row=i, column=5, padx=5, pady=3)

            start_btn = ttk.Button(btn_frame, text="Start", width=8,
                                   command=lambda s=server.id: self.start_server(s))
            start_btn.pack(side='left', padx=2)

            stop_btn = ttk.Button(btn_frame, text="Stop", width=8,
                                  command=lambda s=server.id: self.stop_server(s))
            stop_btn.pack(side='left', padx=2)

    def setup_console_frame(self):
        """Setup the console output panel with tabs"""
        console_frame = ttk.LabelFrame(self.root, text="Console Output (servers must be started from this Manager)", padding=5)
        console_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=5)
        console_frame.grid_columnconfigure(0, weight=1)
        console_frame.grid_rowconfigure(0, weight=1)

        # Notebook for tabs
        self.console_notebook = ttk.Notebook(console_frame)
        self.console_notebook.grid(row=0, column=0, sticky="nsew")

        # Create console tab for each server
        self.console_texts = {}
        for server in self.servers.values():
            frame = ttk.Frame(self.console_notebook)
            self.console_notebook.add(frame, text=server.name)
            frame.grid_columnconfigure(0, weight=1)
            frame.grid_rowconfigure(0, weight=1)

            # Use Text with Scrollbar instead of ScrolledText for better performance
            text_frame = ttk.Frame(frame)
            text_frame.grid(row=0, column=0, sticky="nsew")
            text_frame.grid_columnconfigure(0, weight=1)
            text_frame.grid_rowconfigure(0, weight=1)

            scrollbar = ttk.Scrollbar(text_frame)
            scrollbar.grid(row=0, column=1, sticky="ns")

            text = tk.Text(text_frame, wrap='word', font=('Consolas', 9),
                          bg='#1e1e1e', fg='#d4d4d4',
                          insertbackground='white',
                          yscrollcommand=scrollbar.set,
                          maxundo=0)  # Disable undo for performance
            text.grid(row=0, column=0, sticky="nsew")
            scrollbar.config(command=text.yview)

            text.insert('end', f"[{server.name}] Start server from this Manager to see output...\n")
            text.config(state='disabled')
            self.console_texts[server.id] = text

            # Clear button
            clear_btn = ttk.Button(frame, text="Clear",
                                   command=lambda t=text: self.clear_console(t))
            clear_btn.grid(row=1, column=0, sticky="e", pady=5)

    def setup_status_bar(self):
        """Setup the status bar"""
        self.status_bar = ttk.Label(self.root, text="Ready", relief='sunken', anchor='w')
        self.status_bar.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 5))

    def log_to_console(self, server_id, message):
        """Log a message to server's console"""
        if server_id in self.console_texts:
            text = self.console_texts[server_id]
            text.config(state='normal')
            timestamp = datetime.now().strftime('%H:%M:%S')
            text.insert('end', f"[{timestamp}] {message}\n")
            text.see('end')
            text.config(state='disabled')

    def clear_console(self, text_widget):
        """Clear a console text widget"""
        text_widget.config(state='normal')
        text_widget.delete('1.0', 'end')
        text_widget.config(state='disabled')

    def start_server(self, server_id):
        """Start a single server, using the port from the UI field"""
        server = self.servers[server_id]

        # Read port from the editable UI field
        if server_id in self.port_vars:
            try:
                new_port = int(self.port_vars[server_id].get())
            except ValueError:
                self.log_to_console(server_id, "Invalid port number")
                return

            old_port = server.config['port']
            if new_port != old_port:
                # Update config and command with the new port
                server.config['port'] = new_port
                cmd = server.config['command']
                # Replace --port XXXX in the command string
                import re
                if re.search(r'--port\s+\d+', cmd):
                    server.config['command'] = re.sub(r'--port\s+\d+', f'--port {new_port}', cmd)
                elif '--port' not in cmd:
                    server.config['command'] = f"{cmd} --port {new_port}"
                # Update PORT env var if present
                if 'PORT' in server.config.get('env', {}):
                    server.config['env']['PORT'] = str(new_port)
                self.log_to_console(server_id, f"Port changed: {old_port} -> {new_port}")

        # Log mode if applicable
        mode_label = ""
        if server.has_modes and server.current_mode:
            mode_label = f" [{server.get_mode_label(server.current_mode)}]"

        server.reset_stats()
        self.log_to_console(server_id, f"Starting {server.name}{mode_label} on port {server.port}...")
        self.set_status(f"Starting {server.name}...")

        def do_start():
            success, msg = server.start()
            self.root.after(0, lambda: self.log_to_console(server_id, msg))
            self.root.after(0, lambda: self.set_status(f"{server.name}: {msg}"))

        threading.Thread(target=do_start, daemon=True).start()

    def stop_server(self, server_id):
        """Stop a single server"""
        server = self.servers[server_id]
        self.log_to_console(server_id, f"Stopping {server.name}...")
        self.set_status(f"Stopping {server.name}...")

        def do_stop():
            success, msg = server.stop()
            self.root.after(0, lambda: self.log_to_console(server_id, msg))
            self.root.after(0, lambda: self.set_status(f"{server.name}: {msg}"))

        threading.Thread(target=do_stop, daemon=True).start()

    def restart_server(self, server_id):
        """Restart a single server"""
        server = self.servers[server_id]
        self.log_to_console(server_id, f"Restarting {server.name}...")
        self.set_status(f"Restarting {server.name}...")

        def do_restart():
            success, msg = server.restart()
            self.root.after(0, lambda: self.log_to_console(server_id, msg))
            self.root.after(0, lambda: self.set_status(f"{server.name}: {msg}"))

        threading.Thread(target=do_restart, daemon=True).start()

    def set_status(self, message):
        """Update status bar"""
        self.status_bar.config(text=message)

    def update_status(self):
        """Update server status indicators periodically"""
        # Run health checks in background threads
        for server in self.servers.values():
            if server.is_running():
                threading.Thread(target=server._do_health_check, daemon=True).start()

        # Update UI (non-blocking, uses cached health status)
        for server_id, server in self.servers.items():
            indicator = self.status_indicators[server_id]
            label = self.status_labels[server_id]
            call_label = self.call_count_labels[server_id]

            if server.is_running():
                if server.check_health():
                    indicator.itemconfig('status', fill='#22c55e', outline='#16a34a')  # Green
                    label.config(text="Running")
                else:
                    indicator.itemconfig('status', fill='#eab308', outline='#ca8a04')  # Yellow
                    label.config(text="Starting...")
            else:
                indicator.itemconfig('status', fill='#6b7280', outline='#4b5563')  # Gray
                label.config(text="Stopped")

            # Update call count
            count = server.tool_call_count
            call_label.config(text=f"{count} call{'s' if count != 1 else ''}")

        # Schedule next update
        self.root.after(3000, self.update_status)

    def update_consoles(self):
        """Update console outputs periodically"""
        max_lines = 1000  # Limit console buffer

        for server_id, server in self.servers.items():
            output = server.get_output()
            if output:
                text = self.console_texts[server_id]
                text.config(state='normal')
                text.insert('end', output)

                # Trim old lines if buffer too large
                line_count = int(text.index('end-1c').split('.')[0])
                if line_count > max_lines:
                    text.delete('1.0', f'{line_count - max_lines}.0')

                text.see('end')
                text.config(state='disabled')

        # Schedule next update
        self.root.after(250, self.update_consoles)

    def on_closing(self):
        """Handle window close"""
        running = [s.name for s in self.servers.values() if s.is_running()]
        if running:
            if messagebox.askyesno("Servers Running",
                                   f"These servers are still running:\n{', '.join(running)}\n\nStop them before closing?"):
                for server in self.servers.values():
                    if server.is_running():
                        server.stop()
        self.root.destroy()


def main():
    root = tk.Tk()

    # Set icon if available
    try:
        icon_path = Path(__file__).parent / "icon.ico"
        if icon_path.exists():
            root.iconbitmap(str(icon_path))
    except:
        pass

    # Apply theme
    style = ttk.Style()
    style.theme_use('clam')

    app = ServerManagerGUI(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()


if __name__ == "__main__":
    main()
