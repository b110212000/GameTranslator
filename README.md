# GameTranslator v0.5.0

Windows 本機中英混合／英文／日文語音 → 繁體中文字幕。原文先顯示，中文完成後補上；浮窗以同一行呈現雙語，主視窗保留完整分段內容。原聲直接送到你選擇的耳機，不會朗讀中文。語音辨識使用 faster-whisper（純英文 `base.en`、GPU 多語 `turbo`、CPU 多語 `small`），翻譯使用 Argos 模型與 CTranslate2，再由 OpenCC 轉為臺灣繁體。

模型安裝完成後，翻譯不需要 API、額度或網路連線。模型管理可查看已安裝模型、下載／取消下載、選擇辨識模型及 CPU/GPU。下載是手動操作，辨識與翻譯不會自動下載。

## 安裝與首次設定（v0.5.0）

給新使用者請提供 `GameTranslator-Setup-v0.5.0.exe`。安裝精靈可分開選擇程式與模型資料夾、選擇 GPU 函式庫、建立桌面與開始功能表捷徑，並提供移除入口。採目前使用者安裝，程式本身不要求管理員權限；VB-CABLE 驅動另依官方方式安裝。

安裝後首次開啟會進入設定引導，按「下載建議模型」依序下載通用、純英文或多語高準確組合，再設定音訊。所有新模型與下載暫存都放在選定的模型資料夾；下載完成後推論只讀本機。安裝包不含已下載模型，也不含開發者的音訊設定、日誌或測試音檔。

「模型管理」可瀏覽、套用新的資料夾，並匯入選取模型。匯入會複製並保留原檔，取消或未完成的模型不會發布為可用；更換位置時須先停止翻譯與下載。完整使用教學在 `使用教學.html`，也能從 App 的「使用教學」按鈕離線開啟。

舊設定尚未指定 `model_directory` 時，會沿用舊版共用快取；指定後只在選定位置尋找模型。Whisper 與 Argos 的載入路徑都已接入同一設定。更新保留原有音訊、語言與字幕設定；模型位置以安裝精靈確認的路徑為準。移除 App 時保留模型、settings.json 與額外使用者檔案。

## 語言怎麼選

| 模式 | 用途與取捨 |
| --- | --- |
| 中英混合（建議） | 多語模型自動辨識；中文保留並轉繁體，英文片段才送入英文翻譯。預設 GPU turbo／CPU small，通常比純英文模式慢。 |
| 純英文 | 英文 base.en，較早出字幕。這個模型不能正確處理中文，中文可能被漏掉或誤聽成英文。 |
| 日文 | 固定日文辨識，預設 Argos 日→英→中兩段翻譯；可能累積語意誤差。 |

中英混合不代表辨識保證正確：短語、噪音、口音與同一句快速換語言仍可能漏字。程式已測試「中文不進英文翻譯」的文字保護；真正的中文／中英混合錄音驗收仍待完成，見 `VALIDATION.md`。原文與繁體結果完全相同時，浮窗只顯示一次，避免重複字幕。

模型管理另有 **NLLB 日文直譯實驗版**。模型採 CC BY-NC 4.0 非商用授權；本機八句比較沒有一致優於 Argos，部分句子嚴重誤譯，所以不設為預設。個人測試可手動切換；商用前須另選允許商用的模型並確認授權。

## 字幕樣式與位置

- 浮窗只顯示最新一段，採透明背景與描邊文字，移除原本的大黑框。原文與繁中在同一行，內容相同時只顯示一次。
- 每次原文或中文內容更新後顯示 **3 秒**，接著自動隱藏。中文稍後補上時重新計時，方便閱讀；舊段翻譯不會把已消失的最新字幕叫回來。
- 按 **「調整字幕位置」**，拖曳藍色預覽條到想要的位置，再按 **「完成定位」** 或雙擊字幕。定位期間預覽保持顯示，完成後恢復滑鼠穿透。位置會儲存，下次啟動沿用。
- **「重設位置」** 可回到主螢幕下方中央。定位以主螢幕為範圍，以相對位置儲存，解析度改變時會縮放並限制在畫面內。
- 過長的雙語句子會以省略號維持單行；完整文字可在主視窗最近字幕查看。按「再次預覽」可重新顯示預覽三秒。

## 遊戲內看不到字幕

請把遊戲的顯示模式設為 **視窗化全螢幕／無邊框**，先按「開始預覽」再切回遊戲確認。VALORANT 可在影像／一般的顯示模式調整；遊戲實測由使用者自行進行。

字幕是 Windows 桌面浮窗，已加入滑鼠穿透、不搶輸入焦點及每秒維持置頂。主視窗可最小化。獨佔全螢幕不能保證顯示桌面浮窗；這不等於沒有收到音訊。可回主視窗查看最近字幕與輸入音量，分辨是顯示問題還是收音問題。

顯示模式差異參考 [Microsoft 的全螢幕與浮窗說明](https://devblogs.microsoft.com/directx/demystifying-full-screen-optimizations/)。目前未驗證多螢幕定位，字幕預設在主螢幕下方。

## 開啟 App

雙擊安裝後的捷徑或發行資料夾中的 `GameTranslator.exe`，完成首次設定後按「開始即時音訊」。標題與 EXE 檔案內容均顯示版號 `0.5.0`。使用 `GameTranslator.exe --start --language mixed` 可選中英混合並自動開始；純英文參數為 `en`，日文為 `ja`。更新檔與既有 `D:\GameTranslator\dist` 可能分開存放，請以視窗版號為準。

首次開始時會載入並暖機模型。等狀態顯示「模型已就緒」後再說所選語言；暖機期間原音仍會轉送到耳機。

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

裝置與語言會儲存在 EXE 旁的 `settings.json`，下次啟動自動還原。要換裝置或語言時先按「停止」，修改後重新開始。App 不改動 Windows 的預設音效裝置。

## 狀態與延遲

- 輸入音量條顯示是否真的收到聲音；持續顯示安靜時，先檢查來源 App 的輸出裝置與音量。
- 有聲音但還沒有字幕時，先確認模型已就緒、語言正確，並在句尾短暫停頓。
- 英文約累積 1 秒、日文約 2.4 秒後開始辨識暫定原文；提前停頓時可以更早出字。後續版本在同一段更新。翻譯由另一個工作執行緒處理，完成後補上；「暫譯」表示仍可能修正。前段翻譯不阻擋下一段原文。
- 偵測到約 0.25 秒安靜會確認句尾；持續發言時英文最多 2.4 秒、日文最多 6 秒一段。日文保留較長上下文，期間仍會更新原文與暫譯，不必等整段說完。
- 浮窗顯示最新一段三秒，主視窗保留最近 6 段完整內容。翻譯依段落與版本編號更新，舊段只回填主視窗，不會搶走新字幕。
- 「辨識 X 秒／翻譯 Y 秒」只計算模型處理時間，不含收音、排隊與句尾等待。語音播放開始至字幕出現的延遲須用整合測試或串流量測另外記錄。
- 訊號判斷採音量門檻。背景音樂、重疊語音及持續噪音仍可能影響切句與準確度。超過 3 秒的待處理音訊會捨棄以避免延遲無限累積。
- 模型或裝置失敗時會在狀態列顯示原因；錯誤記錄在 EXE 旁的 `GameTranslator.log`。
- 安靜超過 8 秒時顯示具體接線提示。GPU 推論失敗會嘗試切 CPU，顯示回退狀態；也可在模型管理預先選 CPU，減少與遊戲爭用 GPU。
- 停止會取消待處理字幕；上一輪模型尚未結束時不能再開一輪。關閉 App 會等目前推論釋放模型，避免背景執行緒與 GPU 函式庫同時退出。

## 開發與安裝模型

使用 Windows Python 3.12；這台電腦的英日辨識與翻譯模型已安裝。新環境需先連線下載一次：

```powershell
cd D:\GameTranslator
py -m pip install -r requirements.txt
py scripts\install_local_translation_model.py
py app.py
```

執行期僅讀取本機 Whisper 快取、Argos 與選用的 NLLB 模型。EXE 使用目前 Windows 使用者已安裝的模型，沒有把大型模型打包在 EXE 內。新版也可直接在模型管理下載，無須操作終端機。

可選 GPU 加速：`powershell -ExecutionPolicy Bypass -File scripts\install_gpu_runtime.ps1`。官方 NVIDIA cuBLAS/cuDNN 函式庫會安裝在專案的 `runtime`，只在 App 程序內載入，不改全域 PATH 或顯示卡驅動。本機 RTX 3050 已測試；缺少可用 GPU 時回退 CPU。可用環境變數 `GAMETRANSLATOR_DEVICE=cpu` 強制 CPU 進行對照測試。

## 建置 EXE

```powershell
py -m pip install pyinstaller
powershell -ExecutionPolicy Bypass -File scripts\build_app.ps1
```

先關閉舊的 GameTranslator。成功後輸出到 `dist\GameTranslator.exe`，開啟時不會出現命令列視窗。版本定義在 `version.py` 與 Windows 資源 `scripts\version_info.txt`，發版時需同步更新。

GPU 函式庫另放在 `dist\runtime`，移動 App 時請一起保留這個資料夾。

建置安裝精靈（使用 Windows 內附的 .NET Framework C# 編譯器，不需另外下載安裝工具）：

```powershell
py scripts\build_setup.py --release dist --work build\setup --output release\GameTranslator-Setup-v0.5.0.exe
```

安裝包會保留第三方與 Python 授權檔，以 SHA-256 核對每個檔案；安裝中斷或檔案被鎖定時會還原原有檔案。無法還原時保留暫存備份並顯示位置。此發行版未做程式碼簽章。

## 本機整合驗證

英文測試音檔由 Windows 語音合成產生；日文實測使用 [Google FLEURS](https://huggingface.co/datasets/google/fleurs) 的公開 CC BY 4.0 音檔，來源及原文存於本機 `work/japanese-fixture.json`，不提交音檔到 Git。不需要遊戲或錄製私人通話。先把接收／播放裝置設定成上表的虛擬音效線與耳機。

```powershell
powershell -ExecutionPolicy Bypass -File scripts\generate_sample_audio.ps1
py scripts\prepare_japanese_sample.py
py app.py --self-test work\source-test.json --test-wav samples\watch_right.wav
py app.py --self-test work\japanese-test.json --test-wav samples\japanese_fleurs.wav --language ja
py -m unittest discover -s tests -v
py scripts\benchmark_streaming.py samples\directions_en.wav --report work\benchmark.json
```

封裝後的 EXE 也支援相同參數。測試會阻擋程序內的 Python socket 連線，播放指定音檔到真實 CABLE Input，驗證原文先顯示、翻譯回填、段落順序、耳機音訊輸出與兩輪啟停。結果寫入指定 JSON 檔。這項測試不驗證實體耳機的聲學輸出，也不代表所有噪音環境的準確度。

僅測試已完成的 WAV 檔則可使用 `py recorded_demo.py`，或加上 `--preview` 顯示字幕浮窗。自訂音檔路徑可接在指令後面；接受未壓縮的 16-bit PCM WAV。

## 背景離線驗證

不開啟視窗、不播放音訊的封裝測試：

```powershell
.\GameTranslator.exe --headless --self-test report.json --test-wav directions_en.wav --language mixed
py scripts\soak_test.py samples\japanese_fleurs.wav --language ja --minutes 5 --silent --report work\soak-ja.json
```

`--headless` 驗證兩輪真實本機模型、原文先出、中文回填、順序與停止釋放；不宣稱驗證桌面顯示或實體耳機。`--silent` 壓力測試使用 PCM 串流，另有真實虛擬音效線測試，不應混為同一種驗收。

中英混合音檔可用 `scripts/generate_mixed_audio.ps1 -OutputDirectory work\mixed` 產生，然後執行 `py scripts\check_mixed_audio.py work\mixed --report work\mixed.json`。需有可用的 Windows Hanhan 中文與 Zira 英文語音；缺少任何一個會明確失敗，不會把空音檔當成通過。

## v0.4.1 更新

- 新增中英混合模式與中文文字保護；保留較快的純英文模式。
- 新增模型管理、下載進度／取消、CPU 選擇及 NLLB 日文直譯實驗選項。
- 浮窗使用穿透、不啟用視窗與持續置頂設定，主畫面說明遊戲顯示模式。
- 新增沒有收到聲音與裝置中斷提示；模型停止後才允許下一輪開始。
- 原生模型明確卸載，翻譯快取改為每個實例持有並在停止時釋放。
- 新增來源隔離、慢翻譯、噪音、GPU 競爭、中英文字保護及靜默封裝驗證。

## v0.3.0 更新

- 加入日文輸入、語言記憶、GPU 語音辨識與 CPU 回退。
- 原文與翻譯分開發布，暫定字幕持續更新，句尾確認；翻譯排隊不阻擋辨識。
- 浮窗與主視窗分段顯示，過期翻譯按版本捨棄，排隊採有界限的最新版本替換。
- 加入字幕順序、慢翻譯、停止取消、模型失敗及原文先出回歸測試。

## v0.2.0 修正

- 增加視窗與 EXE 版號、裝置記憶、輸入音量指示及模型就緒狀態。
- 修正模型啟動失敗未顯示、停止後無法再次開始，以及舊工作回呼覆蓋新狀態的問題。
- 改用直接本機翻譯推論，移除執行時隱式下載句子切分資源的需求。
- 依句尾停頓切分語音，限制音訊堆積；支援單聲道麥克風轉送。
- 打包語音活動偵測資源，加入可在封裝 EXE 執行的完整音訊線路測試。
