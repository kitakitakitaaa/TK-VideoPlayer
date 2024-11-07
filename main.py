import vlc
import time
import os
from pathlib import Path
import tkinter as tk
from tkinter import ttk
import platform
import xml.etree.ElementTree as ET
import json

class MediaPlayer:
    def __init__(self, json_path, width=800, height=600):
        self.json_path = json_path
        self.media_files = []
        
        # tkinterウィンドウの設定
        self.root = tk.Tk()
        self.root.title("Media Player")
        self.root.geometry(f"{width}x{height}")
        self.root.resizable(False, False)
        
        # カーソルを非表示にする
        self.root.config(cursor="none")
        
        # フレームの作成
        self.frame = ttk.Frame(self.root, width=width, height=height)
        self.frame.pack(fill=tk.BOTH, expand=True)
        self.frame.pack_propagate(False)
        
        # VLCインスタンスの設定（オプション追加）
        vlc_args = [
            '--no-xlib',  # Linuxでの警告を抑制
            '--quiet',    # 警告メッセージを抑制
            '--no-video-title-show',  # ビデオタイトルを表示しない
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
        
        # すべてのフレームで初期設定
        self.frame.config(cursor="none")
        
        # グローバルなイベントバインディングを追加
        self.root.bind_all('<Motion>', self.hide_cursor)
    
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
        
        # JSONで指定された順序で動画ファイルのみを追加
        for file_path in file_order:
            ext = Path(file_path).suffix.lower()
            if ext in video_extensions:
                self.media_files.append({
                    'path': file_path,
                    'type': 'video'
                })
    
    def play(self):
        def play_media():
            while True:
                for media in self.media_files:
                    media_path = media['path']
                    
                    media_obj = self.instance.media_new(media_path)
                    self.player.set_media(media_obj)
                    self.player.play()
                    
                    # メディアが読み込まれるまで待機
                    time.sleep(0.5)
                    
                    while self.player.is_playing():
                        self.root.update()  # tkinterウィンドウの更新
                        time.sleep(0.1)
                            
                    if not self.root.winfo_exists():  # ウィンドウが閉じられた場合
                        return
        
        # 別スレッドで再生を開始
        import threading
        thread = threading.Thread(target=play_media, daemon=True)
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
        self.hide_cursor()  # メディア再生時にカーソルを非表示に

def load_config():
    tree = ET.parse('config.xml')
    root = tree.getroot()
    
    config = {
        'json_path': root.find('./paths/settingJson_path').text,
        'width': int(root.find('./display/width').text),
        'height': int(root.find('./display/height').text)
    }
    return config

def main():
    config = load_config()
    player = MediaPlayer(
        json_path=config['json_path'],
        width=config['width'],
        height=config['height']
    )
    player.play()

if __name__ == "__main__":
    main()

