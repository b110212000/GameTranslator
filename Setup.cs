using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using System.Web.Script.Serialization;
using System.Windows.Forms;
using Microsoft.Win32;

[assembly: AssemblyTitle("GameTranslator 安裝精靈")]
[assembly: AssemblyVersion("0.5.0.0")]
[assembly: AssemblyFileVersion("0.5.0.0")]

public class PackageFile { public string Name; public long Size; public string Sha256; }
public class PackageInfo { public string Product; public string Version; public PackageFile[] Files; }
public class Options { public string Directory,Models; public int Profile; public bool Gpu=true,Desktop=true,Integrate=true; }

// Appended ZIP payload, read without loading gigabytes into memory.
public sealed class PayloadStream : Stream {
    FileStream file; long start,length,position;
    public PayloadStream(string path) {
        file=File.OpenRead(path); if(file.Length<16)throw new InvalidDataException("安裝包不完整。");
        file.Position=file.Length-16;
        var reader=new BinaryReader(file,Encoding.UTF8,true);length=reader.ReadInt64();
        if(Encoding.ASCII.GetString(reader.ReadBytes(8))!="GTPACK50" || length<=0 || length>file.Length-16)throw new InvalidDataException("找不到安裝資料，請重新取得完整安裝包。");
        start=file.Length-16-length;
    }
    public override bool CanRead {get{return true;}} public override bool CanSeek {get{return true;}}
    public override bool CanWrite {get{return false;}} public override long Length {get{return length;}}
    public override long Position {get{return position;}set{Seek(value,SeekOrigin.Begin);}}
    public override int Read(byte[] b,int o,int c) {file.Position=start+position;int n=file.Read(b,o,(int)Math.Min(c,length-position));position+=n;return n;}
    public override long Seek(long offset,SeekOrigin origin) {long p=origin==SeekOrigin.Begin?offset:origin==SeekOrigin.Current?position+offset:length+offset;if(p<0||p>length)throw new IOException();return position=p;}
    public override void Flush(){} public override void SetLength(long n){throw new NotSupportedException();}
    public override void Write(byte[] b,int o,int c){throw new NotSupportedException();}
    protected override void Dispose(bool disposing){if(disposing)file.Dispose();base.Dispose(disposing);}
}

public static class Installer {
    public const string RegistryPath=@"Software\Microsoft\Windows\CurrentVersion\Uninstall\GameTranslator";
    public static readonly JavaScriptSerializer Json=new JavaScriptSerializer();
    public static readonly Encoding Utf8=new UTF8Encoding(false);
    public static string OwnPath {get{return Assembly.GetExecutingAssembly().Location;}}
    public static string DefaultDirectory {get{
        using(var key=Registry.CurrentUser.OpenSubKey(RegistryPath)) {
            string path=key==null?null:key.GetValue("InstallLocation") as string;
            if(!String.IsNullOrEmpty(path)&&File.Exists(Path.Combine(path,"GameTranslator.exe")))return path;
        }
        return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"Programs","GameTranslator");
    }}
    public static string DefaultModels {get{return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"GameTranslator","models");}}
    public static string Folder(string value) {
        if(String.IsNullOrWhiteSpace(value)||!Path.IsPathRooted(value))throw new IOException("請選擇完整資料夾路徑。");
        string path=Path.GetFullPath(value).TrimEnd('\\');
        if(path==Path.GetPathRoot(path).TrimEnd('\\'))throw new IOException("請選擇磁碟中的資料夾，不要直接選磁碟根目錄。");
        return path;
    }
    public static string Inside(string root,string relative) {
        if(String.IsNullOrEmpty(relative)||Path.IsPathRooted(relative)||relative.Contains(":"))throw new InvalidDataException("不合法的安裝路徑。");
        string full=Path.GetFullPath(Path.Combine(root,relative.Replace('/',Path.DirectorySeparatorChar)));
        if(!full.StartsWith(Path.GetFullPath(root).TrimEnd('\\')+"\\",StringComparison.OrdinalIgnoreCase))throw new InvalidDataException("檔案超出安裝資料夾。");
        return full;
    }
    public static void Probe(string path) {
        Directory.CreateDirectory(path);string probe=Path.Combine(path,".gt-probe-"+Guid.NewGuid().ToString("N"));
        using(File.Create(probe)){}File.Delete(probe);
    }
    public static string Hash(string path) {using(var input=File.OpenRead(path))using(var sha=SHA256.Create())return BitConverter.ToString(sha.ComputeHash(input)).Replace("-","").ToLowerInvariant();}
    public static void Install(Options options,Action<int,string> progress,Func<bool> cancelled) {
        string root=Folder(options.Directory),models=Folder(options.Models);
        if(Directory.Exists(root)&&!File.Exists(Path.Combine(root,"GameTranslator.exe"))&&Directory.EnumerateFileSystemEntries(root).Any(p=>!Directory.Exists(p)||!(models.Equals(p,StringComparison.OrdinalIgnoreCase)||models.StartsWith(p+"\\",StringComparison.OrdinalIgnoreCase))))throw new IOException("程式資料夾已有其他檔案。請選擇空資料夾，或既有的 GameTranslator 安裝資料夾。");
        foreach(var process in Process.GetProcessesByName("GameTranslator"))try{
            if(String.Equals(process.MainModule.FileName,Path.Combine(root,"GameTranslator.exe"),StringComparison.OrdinalIgnoreCase))throw new IOException("請先關閉正在執行的 GameTranslator，再開始更新。");
        }catch(Win32Exception){}catch(InvalidOperationException){}finally{process.Dispose();}
        Probe(root);Probe(models);
        string stage=Inside(root,".gt-stage-"+Guid.NewGuid().ToString("N"));Directory.CreateDirectory(stage);
        var committed=new List<string>();var warnings=new List<string>();bool cleanupStage=true;
        try{
            using(var payload=new PayloadStream(OwnPath))using(var archive=new ZipArchive(payload,ZipArchiveMode.Read)){
                var entry=archive.GetEntry("package.json");if(entry==null||entry.Length>4*1024*1024)throw new InvalidDataException("安裝清單損壞。");
                PackageInfo info;using(var reader=new StreamReader(entry.Open(),Encoding.UTF8))info=Json.Deserialize<PackageInfo>(reader.ReadToEnd());
                if(info.Product!="GameTranslator"||info.Version!="0.5.0"||info.Files==null)throw new InvalidDataException("安裝版本不符。");
                info.Files=info.Files.Where(f=>options.Gpu||!f.Name.StartsWith("runtime/",StringComparison.OrdinalIgnoreCase)).ToArray();
                if(info.Files.Select(f=>f.Name.ToLowerInvariant()).Distinct().Count()!=info.Files.Length)throw new InvalidDataException("重複的安裝檔案。");
                long total=info.Files.Sum(f=>f.Size),copied=0;
                if(new DriveInfo(Path.GetPathRoot(root)).AvailableFreeSpace<total*2+200*1024*1024)throw new IOException("磁碟空間不足，安裝暫存需約 "+total*2/1048576+" MB。");
                byte[] buffer=new byte[1024*1024];
                foreach(var file in info.Files){
                    if(cancelled())throw new OperationCanceledException();
                    var source=archive.GetEntry(file.Name);if(source==null||source.Length!=file.Size)throw new InvalidDataException("檔案不完整："+file.Name);
                    string path=Inside(stage,"new/"+file.Name);Directory.CreateDirectory(Path.GetDirectoryName(path));
                    using(var input=source.Open())using(var output=File.Create(path)){
                        int count;while((count=input.Read(buffer,0,buffer.Length))>0){if(cancelled())throw new OperationCanceledException();output.Write(buffer,0,count);copied+=count;progress((int)(copied*85/Math.Max(total,1)),"正在安裝："+file.Name);}
                    }
                    if(!String.Equals(Hash(path),file.Sha256,StringComparison.OrdinalIgnoreCase))throw new InvalidDataException("檔案驗證失敗："+file.Name);
                }
                var settings=new Dictionary<string,object>();string settingsPath=Path.Combine(root,"settings.json");
                if(File.Exists(settingsPath))try{settings=Json.Deserialize<Dictionary<string,object>>(File.ReadAllText(settingsPath));if(settings==null)throw new Exception();}catch{throw new IOException("原有 settings.json 無法讀取；請先備份並修復設定再更新。");}
                settings["model_directory"]=models;settings["setup_profile"]=options.Profile;settings["setup_completed"]=false;
                var defaults=new Dictionary<string,object>{{"language",options.Profile==1?"en":"mixed"},{"speech_en","base.en"},{"speech_mixed",options.Profile==2?"auto":"small"},{"speech_ja",options.Profile==2?"auto":"small"},{"device","auto"},{"translation","auto"}};
                foreach(var pair in defaults)if(!settings.ContainsKey(pair.Key))settings[pair.Key]=pair.Value;
                if(!options.Gpu)settings["device"]="cpu";
                File.WriteAllText(Inside(stage,"new/settings.json"),Json.Serialize(settings),Utf8);
                File.WriteAllText(Inside(stage,"new/install-manifest.json"),Json.Serialize(info),Utf8);
                if(cancelled())throw new OperationCanceledException();progress(90,"正在完成安裝，請稍候…");
                foreach(string name in info.Files.Select(f=>f.Name).Concat(new[]{"settings.json","install-manifest.json"})){
                    string target=Inside(root,name),source=Inside(stage,"new/"+name),backup=Inside(stage,"old/"+name);
                    Directory.CreateDirectory(Path.GetDirectoryName(target));Directory.CreateDirectory(Path.GetDirectoryName(backup));
                    if(File.Exists(target))File.Replace(source,target,backup);else File.Move(source,target);committed.Add(name);
                }
                if(options.Integrate){try{Register(root,info);}catch(Exception e){warnings.Add("系統移除項目："+e.Message);}try{Shortcuts(root,options.Desktop);}catch(Exception e){warnings.Add("捷徑："+e.Message);}}
                progress(100,warnings.Count==0?"安裝完成。接著開啟 App 下載模型與設定音訊。":"程式已安裝；"+String.Join("；",warnings));
            }
        }catch(Exception failure){
            var restoreErrors=new List<string>();
            foreach(string name in committed.AsEnumerable().Reverse())try{string target=Inside(root,name),backup=Inside(stage,"old/"+name);if(File.Exists(target))File.Delete(target);if(File.Exists(backup))File.Move(backup,target);}catch(Exception e){restoreErrors.Add(name+": "+e.Message);}
            if(restoreErrors.Count>0){cleanupStage=false;throw new IOException("更新失敗，部分檔案無法還原。備份已保留於 "+stage+"。請關閉 App 後還原。",failure);}throw;
        }finally{
            // Only remove the unique staging directory this invocation created.
            if(cleanupStage&&Path.GetFullPath(stage).StartsWith(root+"\\.gt-stage-",StringComparison.OrdinalIgnoreCase)&&Directory.Exists(stage))try{Directory.Delete(stage,true);}catch(IOException){}
        }
    }
    static void Register(string root,PackageInfo info){using(var key=Registry.CurrentUser.CreateSubKey(RegistryPath)){
        key.SetValue("DisplayName","GameTranslator");key.SetValue("DisplayVersion",info.Version);key.SetValue("InstallLocation",root);
        key.SetValue("DisplayIcon",Path.Combine(root,"GameTranslator.exe"));key.SetValue("UninstallString","\""+Path.Combine(root,"Uninstall.exe")+"\" --uninstall");
        key.SetValue("NoModify",1);key.SetValue("NoRepair",1);key.SetValue("EstimatedSize",(int)(info.Files.Sum(f=>f.Size)/1024));
    }}
    static void Link(string path,string target,string working){dynamic shell=Activator.CreateInstance(Type.GetTypeFromProgID("WScript.Shell"));dynamic link=shell.CreateShortcut(path);link.TargetPath=target;link.WorkingDirectory=working;link.Save();}
    static void Shortcuts(string root,bool desktop){
        string programs=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Programs),"GameTranslator");Directory.CreateDirectory(programs);
        Link(Path.Combine(programs,"GameTranslator.lnk"),Path.Combine(root,"GameTranslator.exe"),root);Link(Path.Combine(programs,"使用教學.lnk"),Path.Combine(root,"docs","使用教學.html"),root);
        if(desktop)Link(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory),"GameTranslator.lnk"),Path.Combine(root,"GameTranslator.exe"),root);
    }
    static void RemoveLink(string path,string root){if(!File.Exists(path))return;dynamic shell=Activator.CreateInstance(Type.GetTypeFromProgID("WScript.Shell"));dynamic link=shell.CreateShortcut(path);string target=link.TargetPath;if(!String.IsNullOrEmpty(target)&&Path.GetFullPath(target).StartsWith(root+"\\",StringComparison.OrdinalIgnoreCase))File.Delete(path);}
    public static void Remove(string directory,bool integrate){
        string root=Folder(directory),manifest=Path.Combine(root,"install-manifest.json");var info=Json.Deserialize<PackageInfo>(File.ReadAllText(manifest));
        if(info.Product!="GameTranslator"||info.Files==null)throw new IOException("找不到有效安裝清單，未移除任何檔案。");
        foreach(var file in info.Files)Inside(root,file.Name);
        foreach(var file in info.Files.OrderBy(f=>f.Name=="GameTranslator.exe"?0:1)){string path=Inside(root,file.Name);if(File.Exists(path)&&String.Equals(Hash(path),file.Sha256,StringComparison.OrdinalIgnoreCase))File.Delete(path);}
        File.Delete(manifest);
        if(integrate){
            string programs=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Programs),"GameTranslator");RemoveLink(Path.Combine(programs,"GameTranslator.lnk"),root);RemoveLink(Path.Combine(programs,"使用教學.lnk"),root);RemoveLink(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory),"GameTranslator.lnk"),root);
            using(var key=Registry.CurrentUser.OpenSubKey(RegistryPath)){bool match=key!=null&&String.Equals(key.GetValue("InstallLocation") as string,root,StringComparison.OrdinalIgnoreCase);if(match){key.Close();Registry.CurrentUser.DeleteSubKey(RegistryPath,false);}}
        }
        // Never recursively delete an installation: preserve models and user files.
        foreach(string folder in info.Files.Select(f=>Path.GetDirectoryName(Inside(root,f.Name))).Distinct().OrderByDescending(f=>f.Length))if(Directory.Exists(folder)&&!Directory.EnumerateFileSystemEntries(folder).Any())Directory.Delete(folder);
    }
}

public sealed class SetupWindow:Form {
    Panel body;Label title;Button back,next,cancel;TextBox appPath,modelPath;ComboBox profile;
    CheckBox gpu,desktop,launch,guide;ProgressBar progress;Label status;int page;bool working,cancelled;Options options;
    public SetupWindow(){
        Text="GameTranslator v0.5.0 安裝精靈";ClientSize=new Size(720,510);Font=new Font("Microsoft JhengHei UI",10);StartPosition=FormStartPosition.CenterScreen;FormBorderStyle=FormBorderStyle.FixedDialog;MaximizeBox=false;BackColor=Color.White;
        var banner=new Panel{Dock=DockStyle.Top,Height=104,BackColor=Color.FromArgb(24,41,64)};Controls.Add(banner);
        title=new Label{Left=28,Top=18,Width=650,Height=34,ForeColor=Color.White,Font=new Font(Font.FontFamily,19,FontStyle.Bold)};banner.Controls.Add(title);
        banner.Controls.Add(new Label{Left=30,Top=62,Width=650,Height=28,ForeColor=Color.FromArgb(193,212,235),Text="本機語音翻譯 · 中英混合／英文／日文 · 原音與雙語字幕"});
        body=new Panel{Left=28,Top=122,Width=664,Height=310};Controls.Add(body);
        back=new Button{Text="上一步",Left=390,Top=456,Width=95,Height=32};back.Click+=(s,e)=>{page--;Render();};Controls.Add(back);
        next=new Button{Text="下一步",Left=493,Top=456,Width=95,Height=32};next.Click+=(s,e)=>Advance();Controls.Add(next);
        cancel=new Button{Text="取消",Left=596,Top=456,Width=95,Height=32};cancel.Click+=(s,e)=>{if(working){cancelled=true;cancel.Enabled=false;}else Close();};Controls.Add(cancel);
        FormClosing+=(s,e)=>{if(working){cancelled=true;e.Cancel=true;}};
        options=new Options{Directory=Installer.DefaultDirectory,Models=Installer.DefaultModels};
        string settings=Path.Combine(options.Directory,"settings.json");if(File.Exists(settings))try{var saved=Installer.Json.Deserialize<Dictionary<string,object>>(File.ReadAllText(settings));if(saved.ContainsKey("model_directory"))options.Models=Convert.ToString(saved["model_directory"]);if(saved.ContainsKey("setup_profile"))options.Profile=Math.Min(2,Math.Max(0,Convert.ToInt32(saved["setup_profile"])));}catch{}
        Render();
    }
    Label TextBlock(string text,int top,int height=45){var label=new Label{Text=text,Left=0,Top=top,Width=655,Height=height};body.Controls.Add(label);return label;}
    TextBox FolderRow(string text,int top){
        var entry=new TextBox{Text=text,Left=0,Top=top,Width=558};body.Controls.Add(entry);var browse=new Button{Text="瀏覽…",Left=567,Top=top-1,Width=88,Height=29};
        browse.Click+=(s,e)=>{using(var dialog=new FolderBrowserDialog{SelectedPath=entry.Text,Description="選擇存放資料夾"})if(dialog.ShowDialog(this)==DialogResult.OK)entry.Text=dialog.SelectedPath;};body.Controls.Add(browse);return entry;
    }
    void Render(){
        body.Controls.Clear();back.Enabled=page>0&&page<4;next.Enabled=true;next.Text=page==3?"開始安裝":page==5?"完成":"下一步";
        title.Text=new[]{"歡迎使用 GameTranslator","選擇程式安裝位置","選擇模型存放位置","確認安裝內容","正在安裝","安裝完成"}[page];
        if(page==0){TextBlock("將遊戲或 Discord 隊友的語音變成繁體中文字幕。",10);TextBlock("這個精靈會協助你：\r\n\r\n• 選擇程式和模型各自存放的位置\r\n• 建立桌面及開始功能表捷徑\r\n• 開啟首次設定，下載所需模型\r\n• 查看音訊接線與字幕操作教學",60,180);TextBlock("Windows 10／11 64 位元；採目前使用者安裝。模型下載需要網路，翻譯在本機執行。",250,55);}
        else if(page==1){
            TextBlock("程式資料夾",0,26);appPath=FolderRow(options.Directory,34);TextBlock("可選其他磁碟。請選可寫入的資料夾；安裝精靈不要求系統管理員權限。",76,50);
            gpu=new CheckBox{Text="包含 NVIDIA GPU 加速檔案（約 1.6 GB；也可使用 CPU）",Checked=options.Gpu,Top=142,Width=655,Height=45};body.Controls.Add(gpu);
            desktop=new CheckBox{Text="建立桌面捷徑",Checked=options.Desktop,Top=204,Width=655};body.Controls.Add(desktop);TextBlock("保留既有音訊設定；更新前請先關閉 GameTranslator。",260);
        }else if(page==2){
            TextBlock("模型資料夾（可以與程式分開，建議預留至少 3 GB）",0,26);modelPath=FolderRow(options.Models,34);TextBlock("首次下載的模型組合",87,27);
            profile=new ComboBox{Left=0,Top=120,Width=655,DropDownStyle=ComboBoxStyle.DropDownList};profile.Items.AddRange(new object[]{"通用：中英混合＋日文，約 800 MB（建議）","純英文：較快、較省空間，約 220 MB","多語高準確：建議 NVIDIA GPU，約 2.4 GB"});profile.SelectedIndex=options.Profile;body.Controls.Add(profile);
            TextBlock("模型會在安裝後由 App 下載。之後可在「模型管理」更換位置或匯入已有模型。\r\n\r\n移除 App 時會保留模型與個人設定。",179,115);
        }else if(page==3){TextBlock("程式："+options.Directory+"\r\n\r\n模型："+options.Models+"\r\n\r\nGPU 加速檔案："+(options.Gpu?"安裝":"略過（使用 CPU）")+"\r\n桌面捷徑："+(options.Desktop?"建立":"不建立"),0,175);TextBlock("完成後請在首次設定按「下載建議模型」。\r\n翻譯遊戲／Discord 聲音還需要 VB-CABLE；教學內附官方連結。",190,85);}
        else if(page==4){next.Enabled=false;back.Enabled=false;progress=new ProgressBar{Left=0,Top=70,Width=655,Height=25};body.Controls.Add(progress);status=TextBlock("準備安裝…",118,140);}
        else{cancel.Visible=false;back.Visible=false;TextBlock("程式已安裝到：\r\n"+options.Directory,4,70);launch=new CheckBox{Text="開啟 GameTranslator，進行首次設定",Checked=true,Top=96,Width=655,Height=32};body.Controls.Add(launch);guide=new CheckBox{Text="開啟使用教學",Checked=true,Top=140,Width=655,Height=32};body.Controls.Add(guide);TextBlock("接下來：下載模型 → 設定接收聲音與耳機 → 開始即時音訊。\r\n程式和模型各自的位置都已儲存。",204,90);}
    }
    void Advance(){try{
        if(page==1){options.Directory=Installer.Folder(appPath.Text);Installer.Probe(options.Directory);options.Gpu=gpu.Checked;options.Desktop=desktop.Checked;}
        if(page==2){options.Models=Installer.Folder(modelPath.Text);Installer.Probe(options.Models);options.Profile=profile.SelectedIndex;}
        if(page==3){page=4;Render();RunInstall();return;}
        if(page==5){if(launch.Checked)Process.Start(Path.Combine(options.Directory,"GameTranslator.exe"));if(guide.Checked)Process.Start(Path.Combine(options.Directory,"docs","使用教學.html"));Close();return;}
        page++;Render();
    }catch(Exception e){MessageBox.Show(this,e.Message,"請確認設定",MessageBoxButtons.OK,MessageBoxIcon.Information);}}
    void RunInstall(){
        working=true;cancelled=false;var worker=new BackgroundWorker{WorkerReportsProgress=true};
        worker.DoWork+=(s,e)=>Installer.Install(options,(p,m)=>worker.ReportProgress(p,m),()=>cancelled);
        worker.ProgressChanged+=(s,e)=>{progress.Value=e.ProgressPercentage;status.Text=(string)e.UserState;if(e.ProgressPercentage>=90)cancel.Enabled=false;};
        worker.RunWorkerCompleted+=(s,e)=>{working=false;cancel.Enabled=true;if(e.Error!=null){MessageBox.Show(this,e.Error is OperationCanceledException?"已取消，原有程式與設定已保留。":"安裝未完成："+e.Error.Message,"安裝結果");page=3;Render();}else{string message=status.Text;page=5;Render();if(message.Contains("程式已安裝；"))MessageBox.Show(this,message,"安裝提醒");}};worker.RunWorkerAsync();
    }
    static void CreateHandles(Control control){IntPtr handle=control.Handle;foreach(Control child in control.Controls)CreateHandles(child);}
    public void CheckHiddenLayout(string images){for(page=0;page<6;page++){
        Render();PerformLayout();foreach(Control control in body.Controls)if(control.Right>body.Width||control.Bottom>body.Height)throw new Exception("安裝頁面超出範圍。");
        if(images!=null){Directory.CreateDirectory(images);CreateHandles(this);using(var bitmap=new Bitmap(Width,Height)){DrawToBitmap(bitmap,new Rectangle(0,0,Width,Height));bitmap.Save(Path.Combine(images,"setup-"+page+".png"),System.Drawing.Imaging.ImageFormat.Png);}}
        if(Visible)throw new Exception("背景檢查不應顯示視窗。");
    }}
}

public static class Program {
    static string Value(string[] args,string key){int index=Array.IndexOf(args,key);return index>=0&&index+1<args.Length?args[index+1]:null;}
    [STAThread] public static int Main(string[] args){
        bool silent=args.Contains("--silent");Mutex mutex=null;bool ownsMutex=false;
        try{
            // Uninstall's short-lived parent only launches a temporary worker;
            // the worker acquires the lock after the parent starts exiting.
            if(!args.Contains("--uninstall")&&!Path.GetFileName(Installer.OwnPath).Equals("Uninstall.exe",StringComparison.OrdinalIgnoreCase)){
                mutex=new Mutex(false,@"Local\GameTranslatorSetup");
                try{ownsMutex=mutex.WaitOne(0);}catch(AbandonedMutexException){ownsMutex=true;}
                if(!ownsMutex)throw new IOException("另一個 GameTranslator 安裝或移除程序正在執行，請等待完成。");
            }
            Application.EnableVisualStyles();Application.SetCompatibleTextRenderingDefault(false);
            if(args.Contains("--self-test")){using(var form=new SetupWindow())form.CheckHiddenLayout(Value(args,"--render-folder"));File.WriteAllText(Value(args,"--self-test"),"{\"version\":\"0.5.0\",\"passed\":true,\"pages\":6,\"visible\":false}");return 0;}
            if(args.Contains("--remove")){string parent=Value(args,"--parent");if(parent!=null)try{Process.GetProcessById(Int32.Parse(parent)).WaitForExit(10000);}catch(ArgumentException){}Installer.Remove(Value(args,"--remove"),!args.Contains("--no-integrate"));if(!silent)MessageBox.Show("已移除程式；模型、個人設定及其他檔案已保留。","GameTranslator");return 0;}
            if(args.Contains("--uninstall")||Path.GetFileName(Installer.OwnPath).Equals("Uninstall.exe",StringComparison.OrdinalIgnoreCase)){
                if(MessageBox.Show("要移除 GameTranslator 嗎？模型與個人設定會保留。","移除 GameTranslator",MessageBoxButtons.YesNo)!=DialogResult.Yes)return 0;
                string copy=Path.Combine(Path.GetTempPath(),"GameTranslator-Uninstall-"+Guid.NewGuid().ToString("N")+".exe");File.Copy(Installer.OwnPath,copy);Process.Start(copy,"--remove \""+Path.GetDirectoryName(Installer.OwnPath)+"\" --parent "+Process.GetCurrentProcess().Id);return 0;
            }
            if(silent){var options=new Options{Directory=Value(args,"--dir"),Models=Value(args,"--models"),Gpu=!args.Contains("--cpu"),Desktop=false,Integrate=!args.Contains("--no-integrate")};Installer.Install(options,(p,m)=>{},()=>false);return 0;}
            Application.Run(new SetupWindow());return 0;
        }catch(Exception e){string report=Value(args,"--error-report");if(report!=null)File.WriteAllText(report,e.ToString());if(!silent&&!args.Contains("--self-test"))MessageBox.Show(e.Message,"GameTranslator 安裝程式",MessageBoxButtons.OK,MessageBoxIcon.Error);return 1;}
        finally{if(ownsMutex)mutex.ReleaseMutex();if(mutex!=null)mutex.Dispose();}
    }
}
