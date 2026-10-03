# OCR wrapper #2: logs every step, tolerant to host differences.
$log = "C:\Users\uglygrave\workbuddy-ai\SteamTasks\build\ocr_err.txt"
$png = "C:\Users\uglygrave\.workbuddy-ai\clipboard-images\clipboard-2026-09-21T17-41-19-460Z-ede37cd5.png"
$out = "C:\Users\uglygrave\workbuddy-ai\SteamTasks\build\ocr_out.txt"
try {
    "host=$([Environment]::Version) psver=$($PSVersionTable.PSVersion)" | Set-Content $log
    Add-Type -AssemblyName System.Runtime.WindowsRuntime | Out-Null
    "assembly loaded: $([System.Reflection.Assembly]::Load("System.Runtime.WindowsRuntime, ContentType=WindowsRuntime").IsDynamic)" | Add-Content $log

    $null = [Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]
    $null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics.Imaging, ContentType = WindowsRuntime]
    $null = [Windows.Media.Ocr.OcrEngine, Windows.Media.Ocr, ContentType = WindowsRuntime]
    $null = [Windows.Globalization.Language, Windows.Globalization, ContentType = WindowsRuntime]
    "winrt types ok" | Add-Content $log

    $asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
            $_.Name -eq "AsTask" -and $_.GetParameters().Count -eq 1 -and
            $_.GetParameters()[0].ParameterType.Name -eq "IAsyncOperation`1"
        })[0]
    "astask found: $($asTask -ne $null)" | Add-Content $log

    function Await($WinRtTask, $ResultType) {
        $t = $asTask.MakeGenericMethod($ResultType).Invoke($null, @($WinRtTask))
        $t.Wait(-1) | Out-Null
        $t.Result
    }

    $imgFile = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($png)) ([Windows.Storage.StorageFile])
    $stream = Await ($imgFile.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
    $decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
    $bitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
    "bitmap ok $($__ dimensions unknown)" | Add-Content $log

    $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
    if (-not $engine) {
        $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage([Windows.Globalization.Language]::new("en-US"))
    }
    "engine: $($engine -ne $null)" | Add-Content $log
    if (-not $engine) {
        Set-Content -Path $out -Value "OCR_ENGINE_UNAVAILABLE"
        exit 2
    }

    $result = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
    Set-Content -Path $out -Value $result.Text
    "OCR_DONE" | Add-Content $log
} catch {
    ("FAIL: " + $_.Exception.Message + "`n" + $_.ScriptStackTrace) | Add-Content $log
    exit 1
}
