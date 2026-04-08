import sys
import os
import asyncio
import uiautomation as auto
import time
from . import save
from .save import save_txt
import re
from difflib import SequenceMatcher
from .transformation import word_to_number

last_full_text = ""


current_sentences : dict[str, int] = {}  # {sentence: stable_count}

def longest_common_prefix(a: str, b: str) -> int:
    i = 0
    max_len = min(len(a), len(b))
    while i < max_len and a[i] == b[i]:
        i += 1
    return i

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

def is_already_saved(sentence: str, threshold: float = 0.85) -> bool:
    """check similarity"""
    for (_,saved) in save.saved_captions:
        if similarity_ratio(sentence, saved) >= threshold:
            return True
    return False

def is_substantial_sentence(s: str) -> bool:
    s = s.strip()
    if len(s) < 5:  
        return False
    # 检查是否只包含符号（不含字母、数字、中文字符）
    if re.match(r'^[^\w\u4e00-\u9fff]*$', s):
        return False
    # filter
    words = s.lower().strip('.!?').split()
    if (len(words) <= 2 and words[0] in ['but', 'and', 'so', 'or', 'basically']) or (len(s) <= 10 and re.match(r'^(但是|而且|所以|或者|基本上|然后|接着|因此|于是|不过)', s)):
        return False
    return True

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
                if is_substantial_sentence(sentence):
                    sentences.append(sentence)
                current = ""
        else:
            current += part
            
        i += 1
    
    # handle last part
    if current.strip():
        sentence = current.strip()
        if is_substantial_sentence(sentence):
            sentences.append(sentence)
    
    return sentences

def is_better_version(new_sentence: str, old_sentence: str) -> bool:
    # core: new is better
    new_s=new_sentence.strip()
    old_s=old_sentence.strip()
    
    # if they are very similar, consider the old one is good enough, no need to replace
    if similarity_ratio(new_s, old_s) >= 0.93:
        return False    

    # zero point two → 0.2 
    new_num_count = len(re.findall(r'\d+\.?\d*', new_s))
    old_num_count = len(re.findall(r'\d+\.?\d*', old_s))
    if new_num_count > old_num_count:
        return True
    
    # more words
    new_words = len(re.findall(r'\b\w+\b', new_s))
    old_words = len(re.findall(r'\b\w+\b', old_s))
    if new_words > old_words + 2:
        return True
    
    # more details
    if len(new_s) > len(old_s) *1.2:
        return True
    
    # more punctuation
    new_punct = len(re.findall(r'[，。！？.,!?]', new_s))   
    old_punct = len(re.findall(r'[，。！？.,!?]', old_s))
    if new_punct > old_punct:
        return True
    
    return False   # 相似但没明显改进，就不替换

def find_and_replace_similar(sentence: str, threshold: float = 0.85, max_time_diff: float = 3.0)-> tuple[None|int, bool]:
    """
    find similar sentence  
    if found and the new sentence is better, replace it and return True,
    otherwise return False
    """
    current_time = time.time()
    for i, (saved_time, saved_text) in enumerate(save.saved_captions):
        if similarity_ratio(sentence, saved_text) >= threshold:
            # if in time window, consider replacing if it's a better version
            if current_time - saved_time <= max_time_diff:
                should_replace = is_better_version(sentence, saved_text)
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

def cleanup_file(filename: str):
    try:
        if not os.path.exists(filename):
            return
        
        with open(filename, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        if not lines:
            return
        
        cleaned_lines : list[str] = []
        i = 0
        
        #remove the duplicate depends on "[UPDATED]" marked sentences, keep the last one which is considered the best version
        while i < len(lines):
            current_line = lines[i].strip()
            if not current_line:
                i += 1
                continue
            
            # find similar sentences in group
            group = [current_line]
            j = i + 1
            while j < len(lines):
                next_line = lines[j].strip()
                if not next_line:
                    j += 1
                    continue
                sim=similarity_ratio(current_line.replace('[UPDATED]', '').strip(), next_line.replace('[UPDATED]', '').strip())
                
                if sim >= 0.8:
                    group.append(next_line)
                    j += 1
                else:
                    break

            # choose the best version in group
            best = group[0]
            for candidate in group[1:]:
                clean_cand = candidate.replace('[UPDATED]', '').strip()
                clean_best = best.replace('[UPDATED]', '').strip()
                
                if is_better_version(clean_cand, clean_best):
                    best = candidate
            
            final_sentence = best.replace('[UPDATED]', '').strip()

            #filter incomplete sentence again, just in case
            if is_incomplete_sentence(final_sentence) and not is_last_line_of_file(j, len(lines)):
                i = j
                continue

            cleaned_lines.append(final_sentence + '\n')
            i = j
        
        
        with open(filename, 'w', encoding='utf-8') as f:
            f.writelines(cleaned_lines)
        
        print(f"\n[CLEANUP] File cleaned: {filename}")
        print(f"  Original lines: {len(lines)}")
        print(f"  Cleaned lines: {len(cleaned_lines)}")
        print(f"  Removed: {len(lines) - len(cleaned_lines)} duplicate lines")
        
    except Exception as e:
        print(f"[CLEANUP ERROR] {e}")


async def hook(filename, exit_event):
    global last_full_text, current_sentences

    STABLE_THRESHOLD = 3  
    MAX_SAVED_SENTENCES = 50  

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
        print(f"Settings: STABLE_THRESHOLD={STABLE_THRESHOLD}, MIN_LENGTH=10, SIMILARITY=0.85")

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

            await asyncio.sleep(0.5) # Adjust the sleep time as needed
        
        # save the last sentences when exit
        for sentence, count in current_sentences.items():
            if sentence in seen_sentences:
                continue
            else:
                print(f"[SAVE ON EXIT] {sentence}")
                seen_sentences.add(sentence)
                save.saved_captions.append((time.time(), sentence))
                await save_txt(filename)
        
        cleanup_file(filename)
        
        print("[EXIT] Done!")

    except Exception as e:
        print(f"Exceptions Caught: {e}")
        return False