'''
This is a module for deduplication functions. 
It includes functions to:
- normalize_sentence for further comparison
- find the longest common prefix between two sentences
- calculate similarity ratio between two sentences
- check if a sentence is substantial (not too short or just symbols)
- determine if a new sentence is a better version of an old one
'''

import os
import re
from difflib import SequenceMatcher

from function.transformation import word_to_number

class Deduplicator:
    def __init__(self):
        pass

    def longest_common_prefix(self,a: str, b: str) -> int:
        i = 0
        max_len = min(len(a), len(b))
        while i < max_len and a[i] == b[i]:
            i += 1
        return i

    def normalize_sentence(self, s: str) -> str:
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

    def similarity_ratio(self, s1: str, s2: str) -> float:
        """calculate the similarity"""
        norm1 = self.normalize_sentence(s1)
        norm2 = self.normalize_sentence(s2)
        return SequenceMatcher(None, norm1, norm2).ratio()

    def is_substantial_sentence(self, s: str) -> bool:
        s = s.strip()
        if len(s) < 5:  
            return False
        # check if it is just symbols or emojis
        if re.match(r'^[^\w\u4e00-\u9fff]*$', s):
            return False
        # filter
        words = s.lower().strip('.!?').split()
        if (len(words) <= 2 and words[0] in ['but', 'and', 'so', 'or', 'basically']) or (len(s) <= 10 and re.match(r'^(但是|而且|所以|或者|基本上|然后|接着|因此|于是|不过)', s)):
            return False
        return True

    def is_better_version(self, new_sentence: str, old_sentence: str) -> bool:
        # core: new is better
        new_s=new_sentence.strip()
        old_s=old_sentence.strip()

        # if they are almost the same, consider them as equal and not replace
        if self.similarity_ratio(new_s, old_s) >= 0.95:
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
        
        return False   

    def cleanup_file(self, filename: str):
        try:
            if not os.path.exists(filename):
                return
            
            with open(filename, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            if not lines:
                return

            def extract(line: str) -> tuple[str, str]:
                """split to timestamp and sentence, also remove [UPDATED] tag if exists"""
                match = re.match(r'(\[\d{2}:\d{2}:\d{2}\])\s*(.*)', line.strip())
                if match:
                    return match.group(1), match.group(2).replace('[UPDATED]', '').strip()
                return '', line.replace('[UPDATED]', '').strip()

            # === Pass 1: group adjacent similar sentences ===
            pass1: list[str] = []
            i = 0
            while i < len(lines):
                current_line = lines[i].strip()
                if not current_line:
                    i += 1
                    continue
                
                _, current_sentence = extract(current_line)
                group = [current_line]
                j = i + 1

                while j < len(lines):
                    next_line = lines[j].strip()
                    if not next_line:
                        j += 1
                        continue
                    _, next_sentence = extract(next_line)
                    if self.similarity_ratio(current_sentence, next_sentence) >= 0.92: 
                        group.append(next_line)
                        j += 1
                    else:
                        break

                best = group[0]
                for candidate in group[1:]:
                    _, clean_cand = extract(candidate)
                    _, clean_best = extract(best)
                    if self.is_better_version(clean_cand, clean_best):
                        best = candidate

                _, best_sentence = extract(best)
                pass1.append(f"{extract(best)[0]} {best_sentence}\n".strip() + '\n')
                i = j

            # === Pass 2: substantial  ===
            pass2: list[str] = []
            for idx,line in enumerate(pass1):
                _, sentence = extract(line)
                if not self.is_substantial_sentence(sentence):
                    print(f"[CLEANUP-P2] Removed non-substantial: {sentence}")
                
                # subset judgement
                is_subset = False
                end_idx = min(idx+3, len(pass1))  # 只看后面3句，避免误删
                for future_idx in range(idx+1, end_idx):
                    future_line = pass1[future_idx]
                    _, future_sentence = extract(future_line)
                    if len(sentence) >= len(future_sentence):
                        continue  # long sentence can't be subset of shorter one
                    
                    # calculate longest common prefix ratio
                    clean_sent = sentence.rstrip('.!?')
                    clean_future = future_sentence.rstrip('.!?')
                    
                    if len(clean_sent) == 0: # empty after stripping, skip subset check and let it be removed by non-substantial filter
                        continue 

                    prefix_len = self.longest_common_prefix(clean_sent, clean_future)
                    if prefix_len / len(clean_sent) >= 0.95:
                        # if the longest common prefix covers most of the shorter sentence, consider it a subset
                        is_subset = True
                        print(f"[CLEANUP-P2] Removed subset: '{sentence}' is subset of '{future_sentence}'")
                        break
                
                if not is_subset:
                    pass2.append(line)

            # === Pass 3: globally deduplicate ===
            pass3: list[str] = []
            for line in pass2:
                _, sentence = extract(line)
                is_dup = False
                for idx, kept_line in enumerate(pass3):
                    _, kept_sentence = extract(kept_line)
                    if self.similarity_ratio(sentence, kept_sentence) >= 0.96:
                        if self.is_better_version(sentence, kept_sentence):
                            pass3[idx] = line  
                            print(f"[CLEANUP-P3] Replaced:\n  OLD: {kept_sentence}\n  NEW: {sentence}")
                        is_dup = True
                        break
                if not is_dup:
                    pass3.append(line)

            with open(filename, 'w', encoding='utf-8') as f:
                f.writelines(pass3)
            
            print(f"\n[CLEANUP] File cleaned: {filename}")
            print(f"  Original lines    : {len(lines)}")
            print(f"  After P1 (group)  : {len(pass1)}")
            print(f"  After P2 (subset) : {len(pass2)}")
            print(f"  After P3 (global) : {len(pass3)}")
            print(f"  Total removed     : {len(lines) - len(pass3)}")

        except Exception as e:
            print(f"[CLEANUP ERROR] {e}")




