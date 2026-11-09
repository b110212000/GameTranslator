"""Translate English spans without sending Chinese text to an English model."""
from functools import lru_cache
import re
from opencc import OpenCC

CJK = re.compile(r'[\u3400-\u9fff]')
ENGLISH_SPAN = re.compile(r"[A-Za-z][A-Za-z0-9]*(?:[\s'’.,!?\-]+[A-Za-z0-9]+)*[.!?]?")


class MixedChineseEnglishTranslator:
    def __init__(self, english=None):
        if english is None:
            from audio_pipeline import LocalTraditionalChineseTranslator
            english = LocalTraditionalChineseTranslator('en')
        self.english = english
        self.to_traditional = OpenCC('s2twp')
        self.route = '中英混合：中文保留、英文翻譯'
        self.translate = lru_cache(maxsize=128)(self._translate)

    def _translate(self, text):
        if not text.strip(): return ''
        if not CJK.search(text): return self.english.translate(text)
        def translate_span(match):
            phrase = match.group()
            # Preserve short letter labels (A/B) and uppercase names/acronyms
            # embedded in Chinese, such as Discord's "DC" or "GPU".
            if len(phrase) == 1 or phrase in {'DC','GPU','CPU','FPS','USB','VR','HP'}:
                return phrase
            return self.english.translate(phrase)
        return self.to_traditional.convert(ENGLISH_SPAN.sub(translate_span, text))

    def close(self):
        self.translate.cache_clear()
        close = getattr(self.english, 'close', None)
        if close: close()
