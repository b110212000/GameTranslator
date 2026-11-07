# GameTranslator v0.2.0

Windows 本機英文語音 → 繁體中文字幕。浮窗同時顯示英文與中文；原聲直接送到你選擇的耳機，不會朗讀中文。語音辨識使用 faster-whisper `base.en`，翻譯使用 Argos 的英文 → 中文模型，透過 CTranslate2 執行，再由 OpenCC 轉為臺灣繁體。

模型安裝完成後，翻譯不需要 API、額度或網路連線。目前辨識來源固定為英文。

## 開啟 App

雙擊 `D:\GameTranslator\dist\GameTranslator.exe`，按「開始即時音訊」。標題與 EXE 檔案內容均顯示版號 `0.2.0`。使用 `GameTranslator.exe --start` 可在開啟後自動開始。

首次開始時會載入並暖機模型。等狀態顯示「模型已就緒」後再說英文；暖機期間原音仍會轉送到耳機。

## 音訊設定

先安裝 VB-Audio Virtual Cable。此 App 使用該驅動提供的虛擬音效裝置，不自行安裝驅動。

| 位置 | 選擇 |
| --- | --- |
| Discord 或其他聲音來源 App 的輸出 | CABLE Input (VB-Audio Virtual Cable) |
| GameTranslator「接收聲音」 | CABLE Output (VB-Audio Virtual Cable)，優先 Windows WASAPI |
| GameTranslator「耳機輸出」 | 實體耳機或喇叭 |
| Discord 的麥克風輸入 | 你的實體麥克風 |

路徑為：來源 App → CABLE Input → CABLE Output → GameTranslator → 耳機與雙語字幕。Input/Output 是虛擬音效線本身的兩端名稱。

Discord 的一般語音通話會把「其他人的聲音」送進這條線。若要用自己的麥克風測試，開啟 Discord「語音與視訊」的麥克風測試，讓自己的聲音回放到 CABLE Input；或直接把 GameTranslator 的接收裝置改成實體麥克風。

裝置選擇會依名稱與音訊 API 儲存在 EXE 旁的 `settings.json`，下次啟動自動還原。要換裝置時先按「停止」，修改後重新開始。App 不改動 Windows 的預設音效裝置。

## 狀態與延遲

- 輸入音量條顯示是否真的收到聲音；持續顯示安靜時，先檢查來源 App 的輸出裝置與音量。
- 有聲音但還沒有字幕時，先確認模型已就緒，說英文並在句尾短暫停頓。
- 偵測到約 0.35 秒安靜就送出一段語音；持續發言則最多約 4 秒一段。辨識與翻譯在背景執行，原音不等待字幕。
- 「本段處理 X 秒」只計算該段辨識與翻譯，不包含說話時間、句尾等待與音訊緩衝；它不是完整的端到端延遲。
- 訊號判斷採音量門檻。背景音樂、重疊語音及持續噪音仍可能影響切句與準確度。超過 3 秒的待處理音訊會捨棄以避免延遲無限累積。
- 模型或裝置失敗時會在狀態列顯示原因；錯誤記錄在 EXE 旁的 `GameTranslator.log`。

## 開發與安裝模型

使用 Windows Python 3.12；這台電腦的兩個模型已安裝。新環境需先連線下載一次：

```powershell
cd D:\GameTranslator
py -m pip install -r requirements.txt
py scripts\install_local_translation_model.py
py app.py
```

執行期僅讀取本機 Whisper 快取與 Argos 模型。EXE 使用目前 Windows 使用者已安裝的模型，沒有把大型模型打包在 EXE 內。

## 建置 EXE

```powershell
py -m pip install pyinstaller
powershell -ExecutionPolicy Bypass -File scripts\build_app.ps1
```

先關閉舊的 GameTranslator。成功後輸出到 `dist\GameTranslator.exe`，開啟時不會出現命令列視窗。版本定義在 `version.py` 與 Windows 資源 `scripts\version_info.txt`，發版時需同步更新。

## 本機整合驗證

測試音檔由 Windows 語音合成產生，不需要遊戲或錄製私人通話。先把接收／播放裝置設定成上表的虛擬音效線與耳機。

```powershell
powershell -ExecutionPolicy Bypass -File scripts\generate_sample_audio.ps1
py app.py --self-test work\source-test.json --test-wav samples\watch_right.wav
```

封裝後的 EXE 也支援相同參數。測試會阻擋程序內的 Python socket 連線，播放指定英文音檔到真實 CABLE Input，驗證 CABLE Output 擷取、耳機音訊輸出、英文／中文字幕浮窗，以及兩輪啟動與停止。結果寫入指定 JSON 檔。這項測試不驗證實體耳機的聲學輸出，也不代表所有噪音環境的準確度。

僅測試已完成的 WAV 檔則可使用 `py recorded_demo.py`，或加上 `--preview` 顯示字幕浮窗。自訂音檔路徑可接在指令後面；接受未壓縮的 16-bit PCM WAV。

## v0.2.0 修正

- 增加視窗與 EXE 版號、裝置記憶、輸入音量指示及模型就緒狀態。
- 修正模型啟動失敗未顯示、停止後無法再次開始，以及舊工作回呼覆蓋新狀態的問題。
- 改用直接本機翻譯推論，移除執行時隱式下載句子切分資源的需求。
- 依句尾停頓切分語音，限制音訊堆積；支援單聲道麥克風轉送。
- 打包語音活動偵測資源，加入可在封裝 EXE 執行的完整音訊線路測試。
