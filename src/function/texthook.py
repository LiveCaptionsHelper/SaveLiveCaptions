import sys
import os
import asyncio
import uiautomation as auto
import time
from . import save
from .save import save_txt
import re

from function.dedup import Deduplicator
from function.config import MIN_LENGTH, SIMILARITY, STABLE_THRESHOLD, MAX_SAVED_SENTENCES

last_full_text = ""
deduper=Deduplicator()


current_sentences : dict[str, int] = {}  # {sentence: stable_count}


def is_already_saved(sentence: str, threshold: float = 0.85) -> bool:
    """check similarity"""
    for (_,saved) in save.saved_captions:
        if deduper.similarity_ratio(sentence, saved) >= threshold:
            return True
    return False

def split_into_sentences(text: str):
    # safe split, avoid splitting numbers like "3.14" or "2023.09.01" or "Ms. Menro"
    pattern = r'([。！？.!?]+(?![0-9]))|((?<![A-Za-z0-9\w])\.(?![A-Za-z0-9]))'
    parts = re.split(pattern, text)

    sentences = []
    i = 0
    current=""

    while i < len(parts):
        part = parts[i]
        if part is None:
            i += 1
            continue
            
        # 处理捕获的标点
        if re.match(r'^[。！？.!?]+$', str(part).strip()):
            current += part
            if current.strip():
                sentence = current.strip()
                if deduper.is_substantial_sentence(sentence):
                    sentences.append(sentence)
                current = ""
        else:
            current += part
            
        i += 1
    
    # handle last part
    if current.strip():
        sentence = current.strip()
        if deduper.is_substantial_sentence(sentence):
            sentences.append(sentence)
    
    return sentences


def find_and_replace_similar(sentence: str, threshold: float = 0.85, max_time_diff: float = 3.0)-> tuple[None|int, bool]:
    """
    find similar sentence  
    if found and the new sentence is better, replace it and return True,
    otherwise return False
    """
    current_time = time.time()
    for i, (saved_time, saved_text) in enumerate(save.saved_captions):
        if deduper.similarity_ratio(sentence, saved_text) >= threshold:
            # if in time window, consider replacing if it's a better version
            if current_time - saved_time <= max_time_diff:
                should_replace = deduper.is_better_version(sentence, saved_text)
                return (i, should_replace)
            else:
                # if it's too old, consider it as a new sentence and don't replace
                return (None, False)
    return (None, False)

def is_incomplete_sentence(s: str) -> bool:
    s = s.strip()
    if not s:
        return True
    if s[-1] in '.。!?！？':
        return False
    # if the sentence doesn't end with punctuation, it's likely incomplete
    if not re.search(r'[.。!?！？]', s):
        return True
    return False

def is_last_line_of_file(current_j: int, total_lines: int) -> bool:
    """if the sentence is in the last 3 lines of the file, consider it as important and keep it"""
    return current_j >= total_lines - 3   

def lc_detect() -> bool:
    try:
        auto.SetGlobalSearchTimeout(0.5)
        
        desktop = auto.GetRootControl()
        captions_window = desktop.Control(
            searchDepth=1,
            ClassName="LiveCaptionsDesktopWindow",
            timeout = 0.2
        )


        if captions_window.Exists(0):
            print ("Live Captions Found")
            return True
        else:
            print(f"Live Captions Not Found")
            return False

    except Exception as e:
        print(f"Live Captions Not Found: {str(e)[:50]}...")
        return False


async def hook(filename, exit_event):
    global last_full_text, current_sentences

    seen_sentences = set()  # for quick lookup of already saved sentences

    try:
        if not lc_detect():
            return False

        desktop = auto.GetRootControl()
        captions_window = desktop.Control(
            searchDepth=1,
            ClassName="LiveCaptionsDesktopWindow"
        )
        await asyncio.sleep(1)  # Wait for the window not to be empty
        captions_scrollviewer = captions_window.Control(
            searchDepth=5,
            AutomationId="CaptionsScrollViewer",
            ClassName="ScrollViewer"
        )

        print("Start capture...")
        print(f"Settings: STABLE_THRESHOLD={STABLE_THRESHOLD}, MIN_LENGTH={MIN_LENGTH}, SIMILARITY={SIMILARITY}")

        while not exit_event.is_set():
            current_text = captions_scrollviewer.Name.strip()

            if not current_text:
                await asyncio.sleep(0.5)  
                continue

            sentences = split_into_sentences(current_text)

            current_frame_sentences = set(sentences)

            new_current_sentences = {}
            
            for sentence in current_frame_sentences:
                # filter incomplete sentence
                if is_incomplete_sentence(sentence):
                    continue
                similar_index, should_replace = find_and_replace_similar(sentence)
                
                if similar_index is not None:
                    if should_replace:
                        old_time,old_sentence = save.saved_captions[similar_index]
                        save.saved_captions[similar_index] = (old_time, sentence)
                        seen_sentences.discard(old_sentence)  # remove old sentence from seen set
                        seen_sentences.add(sentence)  # add new sentence to seen set
                        print(f"[REPLACE]")
                        print(f"  OLD: {old_sentence}")
                        print(f"  NEW: {sentence}")
                        await save_txt(filename)
                    continue
                
                if sentence in current_sentences:
                    new_current_sentences[sentence] = current_sentences[sentence] + 1
                else:
                    new_current_sentences[sentence] = 1
                
                if new_current_sentences[sentence] >= STABLE_THRESHOLD:
                    if not any(sentence == s for s in seen_sentences):
                        print(f"[SAVE] {sentence}")
                        seen_sentences.add(sentence)
                        save.saved_captions.append((time.time(), sentence))
                        await save_txt(filename)
                        
                        # set a limit to remove sentences peridically
                        # make same sentences which occurs after a kind of loop will be normally recorded
                        if len(save.saved_captions) >= MAX_SAVED_SENTENCES:
                            save.saved_captions.pop(0)  
            
            current_sentences = new_current_sentences
            
            last_full_text = current_text

            await asyncio.sleep(0.25) # Adjust the sleep time as needed

    except Exception as e:
        print(f"Exceptions Caught: {e}")
        return False

    finally:    
        # save the last sentences when exit
        for sentence, _ in current_sentences.items():
            if sentence in seen_sentences:
                continue
            else:
                print(f"[SAVE ON EXIT] {sentence}")
                seen_sentences.add(sentence)
                save.saved_captions.append((time.time(), sentence))
                await save_txt(filename)
        
        await asyncio.to_thread(deduper.cleanup_file, filename)
        
        print("[EXIT] Done!")