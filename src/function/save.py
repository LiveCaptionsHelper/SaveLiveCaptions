import sys
import os
import asyncio
import tkinter as tk
from tkinter import filedialog
import time
import aiofiles
from difflib import SequenceMatcher
import re
from function.transformation import word_to_number

file_handle=None
saved_captions: list[tuple[float, str]] = [] # time, caption
save_dir = ""

def normalize_sentence(s: str) -> str:
    s = s.strip()
    # space
    s = re.sub(r'\s+', ' ', s)
    # lower letter
    s = s.lower()
    # "twenty twenty six" -> "2026"
    s = word_to_number(s)
    # symbol
    s = re.sub(r'\s+([.,!?])', r'\1', s)
    return s

def similarity_ratio(s1: str, s2: str) -> float:
    """calculate the similarity"""
    norm1 = normalize_sentence(s1)
    norm2 = normalize_sentence(s2)
    return SequenceMatcher(None, norm1, norm2).ratio()

def choose_save_dir():
    global save_dir
    
    timestamp = time.strftime("%Y-%m-%d_%H-%M-%S", time.localtime())  

    if not save_dir:
        root = tk.Tk()
        root.withdraw()  
        save_dir = filedialog.askdirectory(
            title="choose direction",
            initialdir=os.path.expanduser("~")  
        )
        root.destroy()  

        if not save_dir:
            save_dir = os.path.expanduser("~/Documents/captions")
            os.makedirs(save_dir, exist_ok=True)
    
    filename = os.path.join(save_dir, f"{timestamp}_captions.txt")
    
    return filename

async def sort_captions(filename):
    def extract_time(line):
        match = re.match(r'\[(\d{2}:\d{2}:\d{2})\]', line)
        if match:
            time_str = match.group(1)
            return time.strptime(time_str, "%H:%M:%S")
        return None
    with open(filename, "r", encoding="utf-8") as f:
        lines = f.readlines()

    lines.sort(key=extract_time)

    with open(filename, "w", encoding="utf-8") as f:
        f.writelines(lines)


async def save_txt(filename,new_caption: tuple[float, str]):
    ''' Add new caption '''

    global file_handle
    if file_handle is None:
        file_handle = await aiofiles.open(filename, "a+", encoding="utf-8")
    
    t, cap = new_caption
    t_formatted = time.strftime("%H:%M:%S", time.localtime(t))
    
    # write file
    async with aiofiles.open(filename, "a", encoding="utf-8") as f:
        await f.write(f"[{t_formatted}] {cap}\n")

async def close_file():
    global file_handle
    if file_handle is not None:
        await file_handle.close()
        file_handle = None
