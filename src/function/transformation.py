'''
Convert spoken numbers to digits for sentence comparison.

Live Captions sometimes writes the same number as words and later as digits
("twenty twenty six" / "2026"). The deduplicator normalizes sentences with
word_to_number() before comparing them, so that both versions look alike.
The saved transcript text is never changed by this module.

    "twenty six"               -> "26"
    "three hundred and five"   -> "305"
    "two thousand twenty six"  -> "2026"
    "twenty twenty six"        -> "2026"   years spoken in pairs
    "nineteen eighty"          -> "1980"
    "twenty oh eight"          -> "2008"
    "a hundred"                -> "100"
    "twenty first"             -> "21st"
    "one two three"            -> "1 2 3"  digits read out one by one

Only whole words are converted: "often", "someone" or "a cat" stay as they are.
'''
import copy
import re

UNITS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9,
}
TEENS = {
    "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
}
TENS = {
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}
SCALES = {"thousand": 1_000, "million": 1_000_000, "billion": 1_000_000_000}

# ordinal -> (value, kind of the cardinal it behaves like, suffix)
ORDINALS = {
    "first": (1, "unit", "st"), "second": (2, "unit", "nd"), "third": (3, "unit", "rd"),
    **{w: (v, "unit", "th") for w, v in [
        ("fourth", 4), ("fifth", 5), ("sixth", 6), ("seventh", 7), ("eighth", 8), ("ninth", 9)]},
    **{w: (v, "teen", "th") for w, v in [
        ("tenth", 10), ("eleventh", 11), ("twelfth", 12), ("thirteenth", 13), ("fourteenth", 14),
        ("fifteenth", 15), ("sixteenth", 16), ("seventeenth", 17), ("eighteenth", 18),
        ("nineteenth", 19)]},
    **{w: (v, "tens", "th") for w, v in [
        ("twentieth", 20), ("thirtieth", 30), ("fortieth", 40), ("fiftieth", 50),
        ("sixtieth", 60), ("seventieth", 70), ("eightieth", 80), ("ninetieth", 90)]},
}

CARDINALS = [*UNITS, *TEENS, *TENS, "zero", "hundred", *SCALES]


def _alternatives(words) -> str:
    # Longest first, so "nineteen" is tried before "nine"
    return "|".join(sorted(words, key=len, reverse=True))


_SEP = r"[\s-]+"
_NUMBER = rf"(?:{_alternatives(CARDINALS)})"
_UNIT = rf"(?:{_alternatives(UNITS)})"
# A phrase starts with a number word, or "a" directly before hundred/thousand/...
_START = rf"(?:{_NUMBER}|a(?={_SEP}(?:hundred|{_alternatives(SCALES)})\b))"
# ... continues with more number words, optionally joined by "and";
# "oh" only counts as zero before a digit ("twenty oh eight")
_CONTINUE = rf"(?:{_SEP}(?:and{_SEP})?(?:{_NUMBER}|oh(?={_SEP}{_UNIT}\b))\b)"
# ... and may end with an ordinal ("twenty first")
_ORDINAL_END = rf"(?:{_SEP}(?:and{_SEP})?(?:{_alternatives(ORDINALS)})\b)"

NUM_PATTERN = re.compile(rf"\b{_START}\b{_CONTINUE}*{_ORDINAL_END}?", re.IGNORECASE)


def _classify(word: str) -> tuple[str, int, str]:
    '''Return (kind, value, ordinal suffix) for one number word.'''
    if word in UNITS:
        return "unit", UNITS[word], ""
    if word in TEENS:
        return "teen", TEENS[word], ""
    if word in TENS:
        return "tens", TENS[word], ""
    if word in SCALES:
        return "scale", SCALES[word], ""
    if word in ORDINALS:
        value, kind, suffix = ORDINALS[word]
        return kind, value, suffix
    if word in ("zero", "oh"):
        return "zero", 0, ""
    if word == "a":
        return "unit", 1, ""
    if word == "hundred":
        return "hundred", 100, ""
    raise ValueError(word)


class _Number:
    '''One spoken number, assembled word by word following English grammar.'''

    def __init__(self) -> None:
        self.total = 0        # completed thousands / millions / billions
        self.current = 0      # the part below the last scale word
        self.last = ""        # kind of the previous word
        self.leading_zero = False
        self.suffix = ""      # ordinal suffix; an ordinal always ends the number

    def add(self, word: str) -> bool:
        '''Add the word if it continues this number; return False if it cannot.'''
        if self.suffix:
            return False
        kind, value, suffix = _classify(word)
        last = self.last

        if kind == "zero":
            ok = last == ""
        elif kind == "unit":
            ok = last in ("", "tens", "hundred", "scale", "zero")
        elif kind in ("teen", "tens"):
            ok = last in ("", "hundred", "scale")
        elif kind == "hundred":
            ok = last in ("unit", "teen", "tens") and 0 < self.current < 100
        else:  # scale
            ok = (last in ("unit", "teen", "tens", "hundred") and self.current > 0
                  and self.total % (value * 1000) == 0)
        if not ok:
            return False

        if kind == "zero":
            self.leading_zero = True
        elif kind in ("unit", "teen", "tens"):
            self.current += value
        elif kind == "hundred":
            self.current *= 100
        else:
            self.total += self.current * value
            self.current = 0
        self.last = kind
        self.suffix = suffix
        return True

    def accepts(self, word: str) -> bool:
        return copy.copy(self).add(word)

    def two_digit_value(self) -> int | None:
        '''10-99 (or 1-9 after "oh") when the number is a single pair of digits.'''
        if self.total or self.suffix or not 0 <= self.current <= 99:
            return None
        if self.leading_zero:
            return self.current if 1 <= self.current <= 9 else None
        return self.current if self.current >= 10 else None

    def text(self) -> str:
        digits = str(self.total + self.current)
        if self.leading_zero and self.current:
            digits = "0" + digits
        return digits + self.suffix


def _convert_phrase(phrase: str) -> str:
    words = re.split(_SEP, phrase.lower())
    parts: list[_Number | str] = []
    number: _Number | None = None

    for i, word in enumerate(words):
        if word == "and":
            following = words[i + 1] if i + 1 < len(words) else ""
            if number is not None and number.last in ("hundred", "scale") and number.accepts(following):
                continue  # "three hundred and five"
            number = None
            parts.append(word)  # a real "and": "five and six"
            continue

        if number is not None and number.add(word):
            continue
        number = _Number()
        if word not in ORDINALS and number.add(word):
            parts.append(number)
        else:
            # Cannot start a number on its own: "one second", "hundred"
            number = None
            parts.append(word)

    # Years are often spoken as two pairs of digits: "nineteen | eighty",
    # "twenty | twenty six", "twenty | oh eight"
    out: list[str] = []
    i = 0
    while i < len(parts):
        part = parts[i]
        following = parts[i + 1] if i + 1 < len(parts) else None
        if isinstance(part, _Number) and isinstance(following, _Number):
            century, year = part.two_digit_value(), following.two_digit_value()
            if century is not None and century >= 10 and not part.leading_zero and year is not None:
                out.append(f"{century}{year:02d}")
                i += 2
                continue
        out.append(part.text() if isinstance(part, _Number) else part)
        i += 1
    return " ".join(out)


def word_to_number(text: str) -> str:
    '''Replace every spoken number in text with digits.'''
    return NUM_PATTERN.sub(lambda m: _convert_phrase(m.group()), text)
