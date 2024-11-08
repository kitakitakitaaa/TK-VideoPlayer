import vlc
import time
import os
from pathlib import Path
import tkinter as tk
from tkinter import ttk
import platform
import xml.etree.ElementTree as ET
import json
from screeninfo import get_monitors
import socket
import threading

class MediaPlayer:
    def __init__(self, json_path, width=800, height=600, monitor=0):
        # デバッグ用：設定値の確認
        print(f"設定値: width={width}, height={height}, monitor={monitor}")
        
        self.json_path = json_path
        self.media_files = []
        
        # tkinterウィンドウの設定
        self.root = tk.Tk()
        self.root.title("Media Player")
        self.root.configure(bg='black')  # ルートウィンドウの背景を黒に設定
        
        # タイトルバーを消す
        self.root.overrideredirect(True)
        
        # ウィンドウを最前面に固定
        self.root.attributes('-topmost', True)
        
        # 現在のウィンドウサイズを確認
        print(f"初期ウィンドウサイズ: {self.root.winfo_width()}x{self.root.winfo_height()}")
        
        # 明示的にウィンドウサイズを設定
        self.root.minsize(width, height)
        self.root.maxsize(width, height)
        self.root.resizable(False, False)
        
        # 指定したモニターの位置とサイズを取得
        monitors = self.get_monitor_info()
        if monitor < len(monitors):
            mon = monitors[monitor]
            x = mon['x']
            y = mon['y']
            self.root.geometry(f"{width}x{height}+{x}+{y}")
        else:
            self.root.geometry(f"{width}x{height}")
        
        # 強制的に更新
        self.root.update_idletasks()
        
        # 設定後のウィンドウサイズを確認
        print(f"設定後のウィンドウサイズ: {self.root.winfo_width()}x{self.root.winfo_height()}")
        
        # フレームの設定
        self.frame = ttk.Frame(self.root)
        self.frame.pack(fill=tk.BOTH, expand=True)
        self.frame.configure(width=width, height=height)
        self.frame.pack_propagate(False)
        
        # フレームの背景色を黒に設定
        style = ttk.Style()
        style.configure('TFrame', background='black')
        self.frame.configure(style='TFrame')
        
        # カーソルを非表示にする
        self.root.config(cursor="none")
        
        # VLCインスタンスの設定（オプション追加）
        vlc_args = [
            '--no-xlib',  # Linuxでの警告を抑制
            '--quiet',    # 警告メッセージを抑制
            '--no-video-title-show',  # ビデオタイトルを表示しい
            '--no-snapshot-preview',   # スナップショットプレビューを無効化
            '--directx-device=default' # DirectXデバイスをデフォルトに設定
        ]
        self.instance = vlc.Instance(vlc_args)
        self.player = self.instance.media_player_new()
        
        # VLCプレイヤーをtkinterウィンドウに埋め込む
        if platform.system() == "Windows":
            self.player.set_hwnd(self.frame.winfo_id())
        else:
            self.player.set_xwindow(self.frame.winfo_id())
        
        # VLCプレーヤーの表示領域でもカーソルを非表示にする
        self.frame.bind('<Enter>', lambda e: self.frame.config(cursor="none"))
        self.frame.config(cursor="none")
        
        self.load_media_files()
        
        # アスペクト比の設定を変更
        self.player.video_set_scale(0)  # 自動スケーリングを有効化
        
        # すべてのレームで初期設定
        self.frame.config(cursor="none")
        
        # ESCキーのバインディングを修正（フルスクリーン解除ではなく、アプリケーションを終了）
        self.root.bind('<Escape>', lambda e: self.stop())
        
        # グローバルなイベントバインディングを追加
        self.root.bind_all('<Motion>', self.hide_cursor)
        
        # モター情報の取得と設定
        monitors = get_monitors()
        if 0 <= monitor < len(monitors):
            target_monitor = monitors[monitor]
            self.monitor_x = target_monitor.x
            self.monitor_y = target_monitor.y
            self.monitor_width = target_monitor.width
            self.monitor_height = target_monitor.height
            
            # ウィンドウを指定モニターに配置し、そのモニターのサイズに合わせる
            self.root.geometry(f"{self.monitor_width}x{self.monitor_height}+{self.monitor_x}+{self.monitor_y}")
            self.root.update()
        
        # UDP受信用のソケットを設定
        self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp_socket.bind(('127.0.0.1', 12345))  # ローカルホストのポート5000で待ち受け
        self.udp_socket.setblocking(False)  # ノンブロッキングモードに設定
        
        # 現在の再生インデックスを追加
        self.current_index = 0
    
    def hide_cursor(self, event=None):
        """カーソルを強制的に非表示にする"""
        self.root.config(cursor="none")
        self.frame.config(cursor="none")
    
    def load_media_files(self):
        # JSONファイルから再生順序を読み込む
        with open(self.json_path, 'r') as f:
            settings = json.load(f)
            file_order = settings.get('file_order', [])
        
        # 動画ファイルの拡張子
        video_extensions = ['.mp4', '.avi', '.mov', '.mkv', '.wmv']
        
        # 既存のメディアファイルリストをクリア
        self.media_files = []
        
        # インデックス0から処理するように並び替え
        for i in range(len(file_order)):
            file_path = file_order[i]
            ext = Path(file_path).suffix.lower()
            if ext in video_extensions:
                self.media_files.append({
                    'path': file_path,
                    'type': 'video',
                    'index': i  # インデックスを保存（必要な場合）
                })
    
    def play(self):
        def play_media():
            last_check_time = time.time()
            check_interval = 0.1  # UDPチェックの間隔（秒）
            
            while True:
                current_time = time.time()
                
                # UDPメッセージのチェックを一定間隔でのみ実行
                if current_time - last_check_time >= check_interval:
                    try:
                        data, addr = self.udp_socket.recvfrom(1024)
                        message = data.decode('utf-8').strip()
                        print(f"受信したコマンド: {message}")
                        
                        if message == 'video_reload':
                            print("動画リロードコマンドを受信")
                            self.player.stop()
                            self.load_media_files()
                            self.current_index = 0
                            self._play_next_media()
                            last_check_time = current_time
                            continue
                        elif message == 'play':
                            print("開始コマンドを実行")
                            if self.player.get_state() == vlc.State.Paused:
                                self.player.set_pause(0)
                            else:
                                self.player.play()
                        elif message == 'pause':
                            print("一時停止コマンドを実行")
                            self.player.set_pause(1)
                        elif message == 'stop':
                            print("停止コマンドを実行")
                            self.player.stop()
                        elif message == 'next':
                            print("次の動画コマンドを実行")
                            self.player.stop()
                            self.current_index = (self.current_index + 1) % len(self.media_files)
                            self._play_next_media()
                        
                    except BlockingIOError:
                        pass
                    last_check_time = current_time

                # メディア終了時の処理
                if self.player.get_state() == vlc.State.Ended:
                    self.current_index = (self.current_index + 1) % len(self.media_files)
                    self._play_next_media()

                # 必要な時だけウィンドウを更新
                if self.root.winfo_exists():
                    self.root.update()
                else:
                    return

                # スリープ時間を最適化
                time.sleep(0.033)  # 約30FPS相当

        # スレッドを開始
        thread = threading.Thread(target=play_media)
        thread.daemon = True
        thread.start()
        
        # メインループの開始
        self.root.mainloop()
    
    def stop(self):
        self.player.stop()
        self.root.destroy()
    
    def play_next(self):
        # ... existing code ...
        self.hide_cursor()  # 切り替え時にカーソルを非表示に
    
    def play_previous(self):
        # ... existing code ...
        self.hide_cursor()  # 切り替え時にカーソルを非表示に
    
    def play_media(self, file_path):
        # ... existing code ...
        self.hide_cursor()  # メデア再生時にカーソルを非表示に
    
    def get_monitor_info(self):
        """接続されているモニターの情報を取得"""
        monitors = []
        
        try:
            for m in get_monitors():
                monitors.append({
                    'x': m.x,
                    'y': m.y,
                    'width': m.width,
                    'height': m.height
                })
        except Exception:
            # モニター情報の取得に失敗した場合はプライマリディスプレイの情報を使用
            width = self.root.winfo_screenwidth()
            height = self.root.winfo_screenheight()
            monitors.append({
                'x': 0,
                'y': 0,
                'width': width,
                'height': height
            })
        
        return monitors

    def _play_next_media(self):
        """次のメディアファイルを再生する（最適化版）"""
        if len(self.media_files) > 0:
            current_file = self.media_files[self.current_index]
            media_path = current_file['path']
            
            # 同じメディアの重複ロードを防止
            if not hasattr(self, '_last_media_path') or self._last_media_path != media_path:
                print(f"再生開始: index={self.current_index}, path={media_path}")
                media = self.instance.media_new(media_path)
                self.player.set_media(media)
                self._last_media_path = media_path
            
            self.player.play()
            self.hide_cursor()

def load_config():
    tree = ET.parse('config.xml')
    root = tree.getroot()
    
    config = {
        'json_path': root.find('./paths/settingJson_path').text,
        'width': int(root.find('./display/width').text),
        'height': int(root.find('./display/height').text),
        'monitor': int(root.find('./display/monitor').text)  # 追加
    }
    return config

def main():
    config = load_config()
    player = MediaPlayer(
        json_path=config['json_path'],
        width=config['width'],
        height=config['height'],
        monitor=config['monitor']  # 追加
    )
    player.play()

if __name__ == "__main__":
    main()

