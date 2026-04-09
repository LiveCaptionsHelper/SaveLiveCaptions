import sys
import os
import tkinter as tk
import tkinter.messagebox as msgbox
from function.texthook import hook, lc_detect
from function.save import choose_save_dir, close_file
import asyncio

file_handle = None
exit_event = asyncio.Event()
hook_task = None

async def close_all(window):
    global hook_task
    if hook_task is not None:  
        await hook_task
        hook_task = None
    await close_file()
    window.destroy()

def dashboard(loop):
    window = tk.Tk()
    window.title("CatchCaptionsTool")
    window.geometry("60x160")
    window.overrideredirect(True)
    window.wm_attributes("-topmost", True)
    
    if not lc_detect(): 
            msgbox.showerror("Error", "Live Captions Not Found")  
            window.destroy()  
            return
    
    def start_capture():
        global hook_task
        exit_event.clear()  
        start_btn.config(state=tk.DISABLED)
        stop_btn.config(state=tk.NORMAL)  
        filename = choose_save_dir()
        hook_task = loop.create_task(hook(filename,exit_event))  
        

    def stop_capture():
        exit_event.set()
        start_btn.config(state=tk.NORMAL)
        stop_btn.config(state=tk.DISABLED)
        loop.create_task(close_all(window))
    
    def start_move(event):
        window.x = event.x
        window.y = event.y
    
    def stop_move(event):
        window.x = None
        window.y = None
    
    def do_move(event):
        deltax = event.x - window.x
        deltay = event.y - window.y
        x = window.winfo_x() + deltax
        y = window.winfo_y() + deltay
        window.geometry(f"+{x}+{y}")
    
    window.bind("<ButtonPress-1>", start_move)
    window.bind("<ButtonRelease-1>", stop_move)
    window.bind("<B1-Motion>", do_move)

    start_btn = tk.Button(window, text="⚫", command=start_capture)
    start_btn.pack(pady=10)
    stop_btn = tk.Button(window, text="◼", command=stop_capture)
    stop_btn.pack(pady=10)

    def poll_loop():
        loop.call_soon(loop.stop)
        loop.run_forever()
        window.after(10, poll_loop)

    window.after(10, poll_loop)
    window.mainloop()

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    dashboard(loop)
