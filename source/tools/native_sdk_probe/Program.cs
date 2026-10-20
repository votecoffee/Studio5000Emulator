using System.Collections.Concurrent;
using System.Diagnostics;
using System.Security.Cryptography;
using System.Text.Json;
using RockwellAutomation.LogixDesigner;
using RockwellAutomation.LogixDesigner.Logging;

// Only the public SDK is used. Inputs and reports belong in private storage.
if (args.Length != 2) return 2;
var options = JsonSerializer.Deserialize<Options>(File.ReadAllText(args[0]))!;
if (options.Operation is not ("connection" or "upload" or "download") || options.Tags.Length > 32 ||
    options.Operation != "connection" && options.Tags.Length != 0)
    return 2;
string Hash() => Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(options.Project))).ToLowerInvariant();
if (Hash() != options.SourceSha256) return 2;
var steps = new List<object>();
var logger = new Capture();
LogixProject? project = null;
bool passed = true;
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

sealed record Options(string Project, string SourceSha256, string CommunicationsPath, string Operation, string[] Tags);
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
