"""NLLB direct Japanese → Traditional Chinese with local-only model loading."""
from functools import lru_cache
import ctranslate2
from tokenizers import Tokenizer
from opencc import OpenCC
from model_catalog import local_model_path


class DirectJapaneseTranslator:
    def __init__(self):
        path = local_model_path('nllb')
        if path is None:
            raise RuntimeError('尚未安裝日文直譯模型，請在「模型管理」下載 NLLB。')
        self.tokenizer = Tokenizer.from_file(str(path/'tokenizer.json'))
        self.model = ctranslate2.Translator(str(path),device='cpu',compute_type='int8',intra_threads=4)
        self.to_traditional = OpenCC('s2twp')
        self.route = '日文→繁中直譯'
        self.translate = lru_cache(maxsize=128)(self._translate)

    def _translate(self,text):
        if not text.strip(): return ''
        tokens = self.tokenizer.encode(text,add_special_tokens=False).tokens
        # This pinned CT2 conversion uses the legacy tokenizer template:
        # text + EOS + source language (see its tokenizer.json).
        source = tokens[:480] + ['</s>', 'jpn_Jpan']
        result = self.model.translate_batch([source],target_prefix=[['zho_Hant']],
            beam_size=4,max_decoding_length=256)[0]
        target = result.hypotheses[0]
        if target and target[0]=='zho_Hant': target=target[1:]
        ids = [self.tokenizer.token_to_id(token) for token in target]
        decoded = self.tokenizer.decode([i for i in ids if i is not None],skip_special_tokens=True)
        return self.to_traditional.convert(decoded.strip())

    def close(self):
        self.translate.cache_clear()
        self.model.unload_model()
        self.model = None
