"""Record direct/pivot outputs and warm processing times on general phrases."""
import json,socket,time
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from audio_pipeline import LocalTraditionalChineseTranslator
from direct_translation import DirectJapaneseTranslator

def offline(*args,**kwargs): raise RuntimeError('Network disabled in comparison')
socket.socket.connect=offline
pivot=LocalTraditionalChineseTranslator('ja')
direct=DirectJapaneseTranslator()
for translator in (pivot,direct): translator.translate('準備ができました。')
phrases=[
    ('右に敵がいます。','右邊有敵人'),
    ('少し待ってください。','請稍等'),
    ('駅はどこですか。','車站在哪裡'),
    ('このファイルを削除しないでください。','請不要刪除這個檔案'),
    ('会議は明日の午後三時に変更されました。','會議改到明天下午三點'),
    ('音は聞こえますが、画面が表示されません。','聽得到聲音但畫面沒有顯示'),
    ('おそらく現地企業の住所が出てくるでしょう。','可能會顯示當地企業的地址'),
    ('インターネットで敵対的環境コースについて検索すると','在網路上搜尋敵對環境課程時'),
]
rows=[]
for text,meaning in phrases:
    row={'source':text,'reference_meaning':meaning}
    for name,translator in [('pivot',pivot),('direct',direct)]:
        started=time.perf_counter();row[name]=translator.translate(text)
        row[name+'_seconds']=round(time.perf_counter()-started,3)
    rows.append(row)
Path('work').mkdir(exist_ok=True)
Path('work/translation-comparison-040.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(rows,ensure_ascii=False,indent=2))
