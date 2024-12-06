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
import sys  # 追加

class MediaPlayer:
    def __init__(self, json_path, width=800, height=600, monitor="0"):
        with open(json_path, 'r', encoding='utf-8') as f:
            settings = json.load(f)
            video_settings = settings.get('video_settings', {})
            network_settings = settings.get('network_settings', {})
            width = int(video_settings.get('width', width))
            height = int(video_settings.get('height', height))
            monitor = int(video_settings.get('monitor', monitor))
            
            # ネットワーク設定を取得
            self.udp_ip = '0.0.0.0'
            self.udp_port = int(network_settings.get('port', 12345))

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
        
        # ESCキーのバインディングを有効化
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
        self.udp_socket.bind((self.udp_ip, self.udp_port))  # source_ipを使用して待ち受け
        self.udp_socket.setblocking(False)  # ノンブロッキングモードに設定
        
        # 現在の再生インデックスを追加
        self.current_index = 0
        
        # フレームバッファの設定
        self.frame_buffer = None
        
        # 起動時に動画があれば再生
        self._play_next_media()
    
    def hide_cursor(self, event=None):
        """カーソルを強制的に非表示にする"""
        self.root.config(cursor="none")
        self.frame.config(cursor="none")
    
    def load_media_files(self):
        """JSONファイルから再生順序を読み込み、その順序通りにメディアファイルをセットする"""
        try:
            # JSONファイルをUTF-8で読み込む
            with open(self.json_path, 'r', encoding='utf-8') as f:
                settings = json.load(f)
                file_order = settings.get('file_order', [])
            
            # 動画ファイルの拡張子
            video_extensions = ['.mp4', '.avi', '.mov', '.mkv', '.wmv']
            
            # 既存のメディアファイルリストをクリア
            self.media_files = []
            
            # file_orderの順序通りにファイルを追加
            for file_path in file_order:
                # パスをUnicode文字列として正規化
                normalized_path = os.path.normpath(file_path)
                ext = Path(normalized_path).suffix.lower()
                if ext in video_extensions:
                    self.media_files.append({
                        'path': normalized_path,
                        'type': 'video'
                    })
            
            print("メディアファイルを読み込みました:")
            for i, media in enumerate(self.media_files):
                print(f"index={i}: {media['path']}")
        
        except UnicodeDecodeError as e:
            print(f"ファイル読み込みエラー: {e}")
            return []
        except Exception as e:
            print(f"予期せぬエラー: {e}")
            return []
    
    def play(self):
        def play_media():
            last_check_time = time.time()
            check_interval = 0.1
            
            while True:
                current_time = time.time()
                
                if current_time - last_check_time >= check_interval:
                    try:
                        data, addr = self.udp_socket.recvfrom(1024)
                        message = data.decode('utf-8').strip()
                        print(f"受信したコマンド: {message}")
                        
                        if message == 'video_reload':
                            print("動画リロードコマンドを受信")
                            self.player.stop()  # 現在の再生を停止
                            
                            # 設定ファイルを再読み込みしてウィンドウサイズを更新
                            with open(self.json_path, 'r', encoding='utf-8') as f:
                                settings = json.load(f)
                                video_settings = settings.get('video_settings', {})
                                width = int(video_settings.get('width', self.root.winfo_width()))
                                height = int(video_settings.get('height', self.root.winfo_height()))
                                monitor = int(video_settings.get('monitor', 0))
                            
                            # ウィンドウの制約を一時的に解除
                            self.root.minsize(1, 1)
                            self.root.maxsize(10000, 10000)
                            self.root.resizable(True, True)
                            
                            # ウィンドウサイズと位置を更新
                            monitors = self.get_monitor_info()
                            if monitor < len(monitors):
                                mon = monitors[monitor]
                                x = mon['x']
                                y = mon['y']
                                self.root.geometry(f"{width}x{height}+{x}+{y}")
                            else:
                                self.root.geometry(f"{width}x{height}")
                            
                            # フレームサイズも更新
                            self.frame.configure(width=width, height=height)
                            
                            # 強制的に更新
                            self.root.update()
                            self.root.update_idletasks()
                            
                            # ウィンドウの制約を再設定
                            self.root.minsize(width, height)
                            self.root.maxsize(width, height)
                            self.root.resizable(False, False)
                            
                            self.load_media_files()  # JSONの順序通りにメディアファイルを再読み込み
                            self.current_index = 0  # インデックスを0にリセット
                            print(f"JSONの先頭から再生を開始します: index={self.current_index}")
                            self._play_next_media()  # 最初から再生開始
                        elif message == 'play':
                            print("開始コマンドを実行")
                            current_state = self.player.get_state()
                            if current_state in [vlc.State.Paused]:
                                self.player.play()
                            elif current_state in [vlc.State.Stopped, vlc.State.NothingSpecial, vlc.State.Ended]:
                                self._play_next_media()
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
                    if not self._play_next_media():
                        time.sleep(1)

                if self.root.winfo_exists():
                    self.root.update()
                else:
                    return

                time.sleep(0.033)

        thread = threading.Thread(target=play_media)
        thread.daemon = True
        thread.start()
        
        self.root.mainloop()
    
    def stop(self):
        """アプリケーションを完全に終了する"""
        try:
            self.player.stop()
            self.udp_socket.close()  # UDPソケットを明示的にクローズ
            self.root.destroy()
            sys.exit(0)  # プログラムを完全に終了
        except Exception as e:
            print(f"終了時エラー: {e}")
            sys.exit(1)  # エラーが発生した場合も強制終了
    
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
        if not self.media_files:
            print("再生可能なメディアファイルがありません")
            return False

        # 全てのファイルをチェック
        attempts = len(self.media_files)
        for _ in range(attempts):
            current_file = self.media_files[self.current_index]
            media_path = current_file['path']
            
            if os.path.exists(media_path):
                try:
                    # メディアパスをUTF-8として扱う
                    media = self.instance.media_new(str(media_path))
                    self.player.set_media(media)
                    result = self.player.play()
                    
                    if result >= 0:  # 再生成功
                        print(f"再生成功: index={self.current_index}, path={media_path}")
                        self.hide_cursor()
                        # SPOUTでレームを送信
                        self._send_frame_to_spout()
                        return True
                    else:
                        print(f"再生失敗: index={self.current_index}, path={media_path}")
                except Exception as e:
                    print(f"再生エラー: {e}")
            else:
                print(f"ファイルが見つかりません: {media_path}")
            
            # 次のファイルを試す
            self.current_index = (self.current_index + 1) % len(self.media_files)
        
        print("再生可能なファイルが見つかりませんでした")
        return False

    def _send_frame_to_spout(self):
        """現在のフレームをSPOUTで送信"""
        if self.player.get_state() == vlc.State.Playing:
            # VLCから現在のフレームを取得
            frame = self.player.video_take_snapshot(0, 'temp.bmp', 0, 0)
            if frame and os.path.exists('temp.bmp'):
                # フレームをSPOUTで送信
                self.spout_sender.sendImage('temp.bmp')
                os.remove('temp.bmp')

def load_config():
    default_settings = {
        'video_settings': {
            'width': 800,
            'height': 600,
            'monitor': 0
        },
        'network_settings': {
            'source_ip': '127.0.0.1',
            'port': 12345
        },
        'file_order': []
    }

    try:
        with open('settings.json', 'r', encoding='utf-8') as f:
            settings = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        print("設定ファイルが見つからないか、読み込めません。デフォルト設定を作成します。")
        store_path = os.path.join(os.path.dirname(__file__), 'store')
        if os.path.exists(store_path):
            video_files = []
            for file in sorted(os.listdir(store_path)):
                if file.lower().endswith(('.mp4', '.avi', '.mov', '.mkv', '.wmv')):
                    video_files.append(os.path.join('store', file))
            default_settings['file_order'] = video_files

        # デフォルト設定を保存
        with open('settings.json', 'w', encoding='utf-8') as f:
            json.dump(default_settings, f, indent=4, ensure_ascii=False)
        
        settings = default_settings

    return settings

def main():
    config = load_config()
    player = MediaPlayer(
        json_path='settings.json',
        width=config['video_settings']['width'],
        height=config['video_settings']['height'],
        monitor=config['video_settings']['monitor']
    )
    player.play()

if __name__ == "__main__":
    main()

