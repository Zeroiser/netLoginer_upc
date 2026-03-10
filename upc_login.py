import os
import sys
import json
import logging
import threading
import time
import subprocess
import requests
from urllib.parse import urlparse
import tkinter as tk
from tkinter import ttk, messagebox
import webbrowser
import pystray
from PIL import Image, ImageTk

def get_resource_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        # PyInstaller 会创建一个临时文件夹，并将路径存入 sys._MEIPASS
        return os.path.join(sys._MEIPASS, relative_path)
    # 开发环境下的当前脚本所在目录
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), relative_path)

# --- 配置与日志 ---
APP_NAME = "netLoginer_upc"
APPDATA_DIR = os.path.join(os.getenv("APPDATA"), APP_NAME)
CONFIG_FILE = os.path.join(APPDATA_DIR, "config.json")
LOG_FILE = os.path.join(APPDATA_DIR, "app.log")

if not os.path.exists(APPDATA_DIR):
    os.makedirs(APPDATA_DIR)

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    encoding="utf-8"
)

# 默认配置
DEFAULT_CONFIG = {
    "username": "",
    "password": "",
    "service": "unicom",
    "auto_connect_wifi": False,
    "target_wifi_name": "UPC",
    "check_interval_mins": 30,
    "start_with_windows": False,
    "enable_auto_login": True
}

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return {**DEFAULT_CONFIG, **json.load(f)}
        except Exception as e:
            logging.error(f"读取配置失败: {e}")
            return DEFAULT_CONFIG
    return DEFAULT_CONFIG

def save_config(config):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=4)
        logging.info("配置已保存")
    except Exception as e:
        logging.error(f"保存配置失败: {e}")

config = load_config()

# --- 核心逻辑 ---
LOGIN_URL = "http://wlan.upc.edu.cn/eportal/InterFace.do?method=login"
REDIRECT_TEST_URL = "http://detectportal.firefox.com/success.txt"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Connection": "keep-alive",
}

def get_current_wifi():
    """获取当前连接的WiFi名称"""
    if sys.platform == "win32":
        try:
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            output = subprocess.check_output('netsh wlan show interfaces', shell=True, text=True, encoding="gbk", errors="ignore", startupinfo=startupinfo)
            for line in output.split('\n'):
                if "SSID" in line and "BSSID" not in line:
                    return line.split(':')[1].strip()
        except Exception as e:
            logging.error(f"获取当前WiFi失败: {e}")
    return None

def is_wifi_available(ssid):
    """检查目标WiFi是否在周围可用列表中"""
    if sys.platform == "win32":
        try:
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            output = subprocess.check_output('netsh wlan show networks', shell=True, text=True, encoding="gbk", errors="ignore", startupinfo=startupinfo)
            for line in output.split('\n'):
                if "SSID" in line and ssid in line:
                    return True
        except Exception as e:
            logging.error(f"目标WiFi {ssid} 可用性检查失败: {e}")
    return False

def connect_to_wifi(ssid):
    """尝试连接指定的WiFi"""
    logging.info(f"正在尝试连接到WiFi: {ssid}...")
    try:
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        subprocess.run(f'netsh wlan connect name="{ssid}"', shell=True, check=True, startupinfo=startupinfo)
        time.sleep(3)
    except Exception as e:
        logging.error(f"连接WiFi失败: {e}")

def get_query_string():
    try:
        logging.info("正在检查网络状态并获取登录参数...")
        response = requests.get(REDIRECT_TEST_URL, headers=HEADERS, timeout=10, allow_redirects=False)
        if response.is_redirect:
            redirect_url = response.headers.get('Location')
            if redirect_url and ".upc.edu.cn" in redirect_url:
                parsed_url = urlparse(redirect_url)
                query_string = parsed_url.query
                login_host = f"{parsed_url.scheme}://{parsed_url.netloc}"
                logging.info(f"获取登录主机成功: {login_host}")
                return query_string, login_host
            else:
                logging.warning("收到了一个非预期的重定向。")
                return None, None
        elif response.status_code == 200:
            logging.info("网络连接正常，无需登录。")
            return None, None
        else:
            logging.warning(f"非预期状态码: {response.status_code}")
            return None, None
    except requests.exceptions.RequestException as e:
        logging.error(f"网络异常: {e}")
        return None, None

def login():
    global config
    if not config["username"] or not config["password"]:
        logging.warning("未配置账号或密码")
        return False
        
    qs, login_host = get_query_string()
    if not qs or not login_host:
        return False

    login_url = f"{login_host}/eportal/InterFace.do?method=login"
    payload = {
        'userId': config["username"],
        'password': config["password"],
        'service': config["service"],
        'queryString': qs,
        'operatorPwd': '',
        'operatorUserId': '',
        'validcode': '',
        'passwordEncrypt': 'false'
    }

    try:
        logging.info("开始发送登录请求...")
        response = requests.post(login_url, data=payload, headers=HEADERS, timeout=10)
        response.encoding = 'utf-8'
        if '"result":"success"' in response.text:
            logging.info("✅ 登录成功！")
            return True
        else:
            try:
                error_msg = response.json().get("message", "未知错误")
            except:
                error_msg = response.text[:50]
            logging.error(f"❌ 登录失败: {error_msg}")
            return False
    except Exception as e:
        logging.error(f"登录请求抛出异常: {e}")
        return False

def network_task():
    global config
    try:
        current_wifi = get_current_wifi()
        logging.info(f"当前WiFi检测为: {current_wifi}")
        
        target = config["target_wifi_name"]
        
        # 若未连接且开启了自动连接
        if current_wifi != target and config["auto_connect_wifi"]:
            if is_wifi_available(target):
                connect_to_wifi(target)
                current_wifi = get_current_wifi()
            else:
                logging.info(f"开启了自动连接，但未在附近搜索到目标 WiFi: {target}")
            
        # 当且仅当目标WiFi符合时进行登录检查
        if current_wifi == target:
            login()
        else:
            logging.info(f"当前未连接至目标WiFi({target})，跳过登录。")
            
    except Exception as e:
        logging.error(f"网络任务错误: {e}")

# --- 守护线程 ---
def background_loop():
    last_log_time = 0
    while True:
        loop_start = time.time()
        
        if config["enable_auto_login"]:
            current_time = time.time()
            # 基础周期检测（每30分钟）
            if current_time - last_log_time >= (config["check_interval_mins"] * 60):
                network_task()
                last_log_time = current_time
                
        time.sleep(600)  # 避免占用高CPU
        # --- 休眠/睡眠唤醒捕捉逻辑 ---
        time_passed = time.time() - loop_start
        if time_passed > 610:
            logging.info(f"检测到系统从睡眠/休眠中恢复 (时间跨越 {int(time_passed)} 秒)，但守护选项未选中")
            if config["enable_auto_login"]:
                logging.info(f"检测到系统从睡眠/休眠中恢复 (时间跨越 {int(time_passed)} 秒)，准备触发网络重连与登录...")
                time.sleep(5)
                network_task()
                last_log_time = time.time()

# --- GUI ---
class AppGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("UPC 校园网自动登录")
        self.root.geometry("450x550")
        self.root.resizable(False, False)
        
        # 配置全局样式
        style = ttk.Style()
        style.theme_use('clam')
        
        # 定义现代感配色和字体
        bg_color = "#f5f6fa"
        self.root.configure(bg=bg_color)
        
        style.configure('TFrame', background=bg_color)
        style.configure('TLabelframe', background=bg_color)
        style.configure('TLabelframe.Label', background=bg_color, font=("Microsoft YaHei", 10, "bold"), foreground="#2f3640")
        style.configure('TLabel', background=bg_color, font=("Microsoft YaHei", 9), foreground="#2f3640")
        style.configure('TCheckbutton', background=bg_color, font=("Microsoft YaHei", 9), foreground="#2f3640")
        style.configure('TButton', font=("Microsoft YaHei", 10), padding=5)
        style.configure('Title.TLabel', font=("Microsoft YaHei", 16, "bold"), foreground="#192a56")

        main_frame = ttk.Frame(root, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # --- 关于按钮 ---
        about_btn = ttk.Button(root, text="关于作者", command=self.show_about, width=8)
        about_btn.place(x=15, y=15)
        
        # 统一标题
        header = ttk.Label(main_frame, text="netLoginer_upc", style='Title.TLabel')
        header.pack(pady=(0, 20))
        
        # --- 账户设置面板 ---
        account_frame = ttk.LabelFrame(main_frame, text="账户设置", padding="15")
        account_frame.pack(fill=tk.X, pady=(0, 15))
        
        ttk.Label(account_frame, text="学号 / 账号:").grid(row=0, column=0, sticky=tk.W, pady=5, padx=5)
        self.user_var = tk.StringVar(value=config["username"])
        ttk.Entry(account_frame, textvariable=self.user_var, width=32).grid(row=0, column=1, pady=5, padx=5)
        
        ttk.Label(account_frame, text="密 码:").grid(row=1, column=0, sticky=tk.W, pady=5, padx=5)
        self.pass_var = tk.StringVar(value=config["password"])
        ttk.Entry(account_frame, textvariable=self.pass_var, show="*", width=32).grid(row=1, column=1, pady=5, padx=5)
        
        ttk.Label(account_frame, text="运 营 商:").grid(row=2, column=0, sticky=tk.W, pady=5, padx=5)
        self.service_var = tk.StringVar(value=config["service"])
        service_combo = ttk.Combobox(account_frame, textvariable=self.service_var, state="readonly", width=30)
        service_combo['values'] = ('cmcc', 'unicom', 'ctcc')
        service_combo.grid(row=2, column=1, pady=5, padx=5)
        
        # --- 网络监控面板 ---
        network_frame = ttk.LabelFrame(main_frame, text="网络监控", padding="15")
        network_frame.pack(fill=tk.X, pady=(0, 20))
        
        ttk.Label(network_frame, text="目标 WiFi:").grid(row=0, column=0, sticky=tk.W, pady=5, padx=5)
        self.wifi_var = tk.StringVar(value=config["target_wifi_name"])
        ttk.Entry(network_frame, textvariable=self.wifi_var, width=32).grid(row=0, column=1, pady=5, padx=5)

        self.auto_connect_var = tk.BooleanVar(value=config["auto_connect_wifi"])
        ttk.Checkbutton(network_frame, text="开启自动连接目标 WiFi", variable=self.auto_connect_var).grid(row=1, column=0, columnspan=2, sticky=tk.W, pady=(10, 5), padx=5)
        
        self.enable_loop_var = tk.BooleanVar(value=config["enable_auto_login"])
        ttk.Checkbutton(network_frame, text="启用守护(每三十分钟、从睡眠中唤醒时检测网络状态)", variable=self.enable_loop_var).grid(row=2, column=0, columnspan=2, sticky=tk.W, pady=(0, 5), padx=5)

        self.start_with_win_var = tk.BooleanVar(value=config["start_with_windows"])
        ttk.Checkbutton(network_frame, text="随 Windows 开机自动静默启动", variable=self.start_with_win_var).grid(row=3, column=0, columnspan=2, sticky=tk.W, pady=(0, 5), padx=5)

        # --- 底部按钮区 ---
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=10)
        
        btn_style = ttk.Style()
        btn_style.configure('Accent.TButton', font=("Microsoft YaHei", 10, "bold"), foreground="blue")
        
        ttk.Button(btn_frame, text="立即登录", command=self.manual_login, width=15).pack(side=tk.LEFT, padx=(5, 5), expand=True)
        ttk.Button(btn_frame, text="查看日志", command=self.open_log, width=10).pack(side=tk.LEFT, padx=(5, 5), expand=True)
        ttk.Button(btn_frame, text="保存所有配置", command=self.save_settings, width=15).pack(side=tk.RIGHT, padx=(5, 5), expand=True)
        
        # --- 日志路径说明 ---
        log_label = tk.Label(main_frame, text=f"日志: {LOG_FILE}", font=("Microsoft YaHei", 8), fg="#7f8fa6", bg=bg_color, wraplength=400, justify="center")
        log_label.pack(side=tk.BOTTOM, pady=15)

    def show_about(self):
        about_win = tk.Toplevel(self.root)
        about_win.title("关于作者")
        about_win.geometry("300x380")
        about_win.configure(bg="#f5f6fa")
        about_win.resizable(False, False)
        about_win.transient(self.root)
        about_win.grab_set()

        # 头像
        try:
            avatar_path = get_resource_path("avatar.png")
            img = Image.open(avatar_path)
            img.thumbnail((80, 80), Image.Resampling.LANCZOS)
            self.avatar_img = ImageTk.PhotoImage(img)

            img_label = tk.Label(about_win, image=self.avatar_img, bg="#f5f6fa")
            img_label.pack(pady=(25, 10))
        except Exception as e:
            logging.error(f"头像加载失败: {e}")
            no_img_label = tk.Label(about_win, text="[请在同目录\n放置 avatar.png]", bg="#e1e2e6", fg="#7f8fa6", width=15, height=6)
            no_img_label.pack(pady=(25, 10))

        tk.Label(about_win, text="Zeroiser", font=("Microsoft YaHei", 12, "bold"), bg="#f5f6fa", fg="#192a56").pack(pady=5)
        tk.Label(about_win, text="netLoginer_upc", font=("Microsoft YaHei", 10), bg="#f5f6fa", fg="#7f8fa6").pack(pady=5)

        github_url = "https://github.com/Zeroiser/netLoginer_upc"
        link_font = ("Microsoft YaHei", 10, "underline")
        link_label = tk.Label(about_win, text="访问项目 GitHub (点击跳转)", font=link_font, fg="#0097e6", cursor="hand2", bg="#f5f6fa")
        link_label.pack(pady=15)
        link_label.bind("<Button-1>", lambda e: webbrowser.open(github_url))

    def open_log(self):
        if os.path.exists(LOG_FILE):
            os.startfile(LOG_FILE)
        else:
            messagebox.showinfo("提示", "日志文件尚不存在。")

    def toggle_autostart(self, enable):
        """利用注册表设置开机自启，--silent 以静默启动"""
        import winreg
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
            if enable:
                exe_path = sys.executable if getattr(sys, 'frozen', False) else f'"{sys.executable}" "{os.path.abspath(__file__)}"'
                cmd = f'{exe_path} --silent'
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, cmd)
                logging.info("已启用开机自启")
            else:
                try:
                    winreg.DeleteValue(key, APP_NAME)
                    logging.info("已禁用开机自启")
                except FileNotFoundError:
                    pass
            winreg.CloseKey(key)
        except Exception as e:
            logging.error(f"设置开机自启失败: {e}")

    def save_settings(self):
        config["username"] = self.user_var.get()
        config["password"] = self.pass_var.get()
        config["service"] = self.service_var.get()
        config["target_wifi_name"] = self.wifi_var.get()
        config["auto_connect_wifi"] = self.auto_connect_var.get()
        config["enable_auto_login"] = self.enable_loop_var.get()
        config["start_with_windows"] = self.start_with_win_var.get()
        save_config(config)
        self.toggle_autostart(config["start_with_windows"])
        messagebox.showinfo("成功", "配置已保存。后台检测已根据新配置更新。")

    def manual_login(self):
        self.save_settings()
        threading.Thread(target=self._run_login, daemon=True).start()
        
    def _run_login(self):
        try:
            messagebox.showinfo("信息", "手动登录指令发送成功...")
            network_task()
            messagebox.showinfo("信息", "手动登录请求发送完毕，请查看日志获取详细结果。")
        except Exception as e:
            messagebox.showerror("错误", f"发生错误: {e}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="UPC Login Task")
    parser.add_argument("--silent", action="store_true", help="Run minimized to system tray.")
    args = parser.parse_args()

    # 启动后台常驻线程 (供保持GUI打开时使用)
    t = threading.Thread(target=background_loop, daemon=True)
    t.start()
    
    # 初始化GUI
    root = tk.Tk()
    app = AppGUI(root)

    # ====== 核心系统托盘逻辑 ======
    def show_window(icon, item):
        icon.stop()
        root.after(0, root.deiconify)

    def quit_window(icon, item):
        icon.stop()
        root.destroy()
        os._exit(0)

    def withdraw_window():
        root.withdraw()
        # 尝试使用相同的头像作为图标给托盘（必须提供 PIL Image）
        try:
            icon_img = Image.open(get_resource_path("avatar.png"))
        except Exception:
            # 创建个纯色的兜底默认占位图标
            icon_img = Image.new('RGB', (64, 64), color=(73, 109, 137))
            
        menu = pystray.Menu(
            pystray.MenuItem('显示面板', show_window, default=True),
            pystray.MenuItem('完全退出程序', quit_window)
        )
        icon = pystray.Icon("name", icon_img, "UPC Login Guard", menu)
        threading.Thread(target=icon.run, daemon=True).start()

    def on_unmap(event):
        # 当窗口被最小化时，拦截并转移到系统托盘
        if root.state() == 'iconic':
            withdraw_window()

    # 拦截原生窗口关闭的叉号（改为最小化到托盘）
    root.protocol('WM_DELETE_WINDOW', withdraw_window)
    # 拦截窗口最小化事件
    root.bind("<Unmap>", on_unmap)

    if args.silent:
        # 如果是带有 --silent 开机静默启动参数，一上来就直接隐藏
        root.withdraw()
        withdraw_window()
        
    root.mainloop()
