using System.Collections.Concurrent;
using System.Diagnostics;
using System.Security.Cryptography;
using System.Text.Json;
using System.Text;
using System.Text.RegularExpressions;
using System.Net.Http;
using RockwellAutomation.LogixDesigner;
using RockwellAutomation.LogixDesigner.Logging;

// Only the public SDK is used. Inputs and reports belong in private storage.
if (args.Length != 2) return 2;
var options = JsonSerializer.Deserialize<Options>(File.ReadAllText(args[0]))!;
if (options.Operation is not ("connection" or "upload" or "download" or "modes") || options.Tags.Length > 32 ||
    options.Operation != "connection" && options.Tags.Length != 0)
    return 2;
string Hash() => Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(options.Project))).ToLowerInvariant();
if (Hash() != options.SourceSha256) return 2;
var steps = new List<object>();
var logger = new Capture();
LogixProject? project = null;
bool passed = true;
using var http = new HttpClient(new HttpClientHandler { AllowAutoRedirect = false }) { Timeout = TimeSpan.FromSeconds(5) };
async Task<JsonElement> Backend(string? mode = null)
{
    if (!Uri.TryCreate(options.BackendUrl, UriKind.Absolute, out var url) || url.Scheme != "http" ||
        !url.IsLoopback || !string.IsNullOrEmpty(url.UserInfo) || string.IsNullOrEmpty(options.InstanceId))
        throw new InvalidOperationException("Mode probe requires a pinned local emulator URL");
    var script = await http.GetStringAsync(new Uri(url, "/session.js"));
    var token = JsonSerializer.Deserialize<string>(Regex.Match(script, "LOGIX_TOKEN = (\".*?\")").Groups[1].Value)!;
    async Task<JsonElement> Call(string action, object body) {
        using var request = new HttpRequestMessage(HttpMethod.Post, new Uri(url, "/api/" + action));
        request.Headers.Add("X-Logix-Token", token);
        request.Content = new StringContent(JsonSerializer.Serialize(body), Encoding.UTF8, "application/json");
        using var response = await http.SendAsync(request);
        response.EnsureSuccessStatusCode();
        var state = JsonDocument.Parse(await response.Content.ReadAsStringAsync()).RootElement.Clone();
        if (state.GetProperty("instance_id").GetString() != options.InstanceId ||
            state.GetProperty("connectivity").GetProperty("native_correlation").GetProperty("source_acd_sha256").GetString() != options.SourceSha256)
            throw new InvalidOperationException("Emulator instance/source changed");
        return state;
    }
    var current = await Call("observe", new {});
    return mode is null ? current : await Call("controller-mode", new { mode });
}
async Task CheckMode(string expected) {
    // The SDK exposes its cached mode; external changes arrive on its status poll.
    string mode = "Unknown";
    var deadline = Stopwatch.StartNew();
    do {
        mode = (await project!.ReadControllerModeAsync()).ToString();
        if (mode == expected) return;
        await Task.Delay(100);
    } while (deadline.Elapsed < TimeSpan.FromSeconds(8));
    throw new InvalidOperationException($"Expected SDK {expected}, got {mode} after status polling");
}
async Task Step(string name, Func<Task<object?>> action)
{
    var clock = Stopwatch.StartNew();
    try
    {
        var value = await action();
        steps.Add(new { method = name, status = "succeeded", value, elapsedMs = clock.Elapsed.TotalMilliseconds });
    }
    catch (Exception error)
    {
        passed = false;
        var chain = new List<object>();
        for (Exception? item = error; item is not null && chain.Count < 16; item = item.InnerException)
            chain.Add(new { type = item.GetType().FullName, message = item.Message, hresult = $"0x{item.HResult:X8}" });
        steps.Add(new { method = name, status = "failed", errors = chain, elapsedMs = clock.Elapsed.TotalMilliseconds });
        throw;
    }
}
try
{
    await Step("OpenLogixProjectAsync", async () => {
        project = await LogixProject.OpenLogixProjectAsync(options.Project, logger); return true;
    });
    await Step("SetCommunicationsPathAsync", async () => {
        await project!.SetCommunicationsPathAsync(options.CommunicationsPath); return true;
    });
    await Step("ReadConnectedStateAsync:initial", async () => (await project!.ReadConnectedStateAsync()).ToString());
    if (options.Operation == "upload")
        await Step("UploadAsync", async () => { await project!.UploadAsync(); return true; });
    else if (options.Operation == "download")
        await Step("DownloadAsync", async () => { await project!.DownloadAsync(); return true; });
    else
    {
        await Step("GoOnlineAsync", async () => { await project!.GoOnlineAsync(); return true; });
        await Step("ReadConnectedStateAsync:online", async () => {
            var state = await project!.ReadConnectedStateAsync();
            if (state != LogixProject.ConnectedState.Online) throw new InvalidOperationException("SDK did not report Online");
            return state.ToString();
        });
        await Step("ReadControllerModeAsync", async () => (await project!.ReadControllerModeAsync()).ToString());
        if (options.Operation == "modes")
        {
            for (int cycle = 1; cycle <= 2; cycle++) {
                await Step("SDK Run advances emulator scans:" + cycle, async () => {
                    var before = await Backend();
                    if (before.GetProperty("controller").GetProperty("mode").GetString() != "Program")
                        throw new InvalidOperationException("Mode probe must start in Program");
                    await project!.ChangeControllerModeAsync(LogixProject.RequestedControllerMode.Run);
                    await CheckMode("Run");
                    await Task.Delay(250);
                    var after = await Backend();
                    if (!after.GetProperty("controller").GetProperty("running").GetBoolean() ||
                        after.GetProperty("scan").GetInt64() <= before.GetProperty("scan").GetInt64() ||
                        after.GetProperty("controller").GetProperty("prescan_count").GetInt64() != before.GetProperty("controller").GetProperty("prescan_count").GetInt64() + 1 ||
                        after.GetProperty("controller").GetProperty("first_scan_pending").GetBoolean())
                        throw new InvalidOperationException("SDK Run did not initialize once and advance scans");
                    return new { scanBefore = before.GetProperty("scan").GetInt64(), scanAfter = after.GetProperty("scan").GetInt64(),
                                 prescanCount = after.GetProperty("controller").GetProperty("prescan_count").GetInt64() };
                });
                await Step("SDK Program stops emulator scans:" + cycle, async () => {
                    await project!.ChangeControllerModeAsync(LogixProject.RequestedControllerMode.Program);
                    await CheckMode("Program");
                    var before = await Backend();await Task.Delay(150);var after = await Backend();
                    if (after.GetProperty("controller").GetProperty("running").GetBoolean() ||
                        after.GetProperty("scan").GetInt64() != before.GetProperty("scan").GetInt64())
                        throw new InvalidOperationException("SDK Program did not stop scans");
                    return after.GetProperty("scan").GetInt64();
                });
            }
            foreach (var mode in new [] { "Run", "Program" })
            {
                await Step("Web control visible to SDK:" + mode, async () => {
                    var before = await Backend();var after = await Backend(mode);await CheckMode(mode);
                    long expected = before.GetProperty("controller").GetProperty("prescan_count").GetInt64() + (mode == "Run" ? 1 : 0);
                    if (after.GetProperty("controller").GetProperty("prescan_count").GetInt64() != expected)
                        throw new InvalidOperationException("Web mode change did not retain the expected initialization count");
                    return mode;
                });
                if (mode == "Run")
                    await Step("Repeated web Run does not repeat prescan", async () => {
                        var before = await Backend();var after = await Backend("Run");
                        if (after.GetProperty("controller").GetProperty("prescan_count").GetInt64() != before.GetProperty("controller").GetProperty("prescan_count").GetInt64())
                            throw new InvalidOperationException("Repeated Run performed another prescan");
                        return after.GetProperty("controller").GetProperty("prescan_count").GetInt64();
                    });
            }
        }
        // Tag-read failures are recorded independently; still attempt cleanup.
        foreach (var tag in options.Tags)
            try { await Step("GetTagValueAsync:" + tag, async () =>
                (await project!.GetTagValueAsync(tag, LogixProject.OperationMode.Online, LogixProject.DataType.BYTE_ARRAY)).ToBase64()); }
            catch { }
        await Step("GoOfflineAsync", async () => { await project!.GoOfflineAsync(); return true; });
        await Step("ReadConnectedStateAsync:final", async () => {
            var state = await project!.ReadConnectedStateAsync();
            if (state != LogixProject.ConnectedState.Offline) throw new InvalidOperationException("SDK did not report Offline");
            return state.ToString();
        });
    }
}
catch { passed = false; }
finally
{
    if (project is not null)
    {
        if (options.Operation == "modes")
            try { await Step("Restore Program", async () => { await Backend("Program"); return true; }); }
            catch { passed = false; }
        try
        {
            // A failed Upload can leave Connected rather than Online.
            if (await project.ReadConnectedStateAsync() != LogixProject.ConnectedState.Offline)
                await Step("GoOfflineAsync:cleanup", async () => { await project.GoOfflineAsync(); return true; });
            await Step("ReadConnectedStateAsync:cleanup", async () => {
                var state = await project.ReadConnectedStateAsync();
                if (state != LogixProject.ConnectedState.Offline) throw new InvalidOperationException("SDK cleanup did not report Offline");
                return state.ToString();
            });
        }
        catch { passed = false; }
        try { project.Dispose(); }
        catch (Exception error) { passed = false; steps.Add(new { method = "Dispose", status = "failed", error = error.Message }); }
    }
}
var unchanged = Hash() == options.SourceSha256;
passed &= unchanged;
await File.WriteAllTextAsync(args[1], JsonSerializer.Serialize(new {
    status = passed ? "succeeded" : "failed", operation = options.Operation,
    sourceUnchanged = unchanged, steps, events = logger.Events.ToArray(),
    eventsTruncated = logger.Truncated, nativeControllerEquivalence = "NOT ASSESSED"
}, new JsonSerializerOptions { WriteIndented = true }));
return passed ? 0 : 1;

sealed record Options(string Project, string SourceSha256, string CommunicationsPath, string Operation, string[] Tags,
                      string? BackendUrl = null, string? InstanceId = null);
sealed class Capture : IOperationEvent
{
    public ConcurrentQueue<object> Events { get; } = new();
    public bool Truncated { get; private set; }
    void Record(string kind, string message, int? value = null)
    {
        if (Events.Count >= 5000) { Truncated = true; return; }
        Events.Enqueue(new { time = DateTimeOffset.UtcNow, kind, message, progress = value });
    }
    public void LogProgress(bool enabled) { }
    public void LogStatus(bool enabled) { }
    public void LogError(bool enabled) { }
    public void Progress(string projectFile, int value) => Record("progress", "SDK progress", value);
    public void Status(string projectFile, string message) => Record("status", message);
    public void Error(string projectFile, string message) => Record("error", message);
}
