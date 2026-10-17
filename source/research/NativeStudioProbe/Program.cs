using System.Security.Cryptography;
using System.Text.Json;
using System.Text.RegularExpressions;
using RockwellAutomation.LogixDesigner;
using RockwellAutomation.LogixDesigner.Logging;

// This diagnostic never downloads, saves, changes controller mode or writes tags.
// GoOnline can correlate the private in-memory project, which is discarded.
var options = new Dictionary<string,string>();
for (int i = 0; i < args.Length; i += 2)
{
    if (i + 1 >= args.Length || !args[i].StartsWith("--")) throw new ArgumentException("Use --acd, --comm-path, --operation and --out");
    options.Add(args[i], args[i + 1]);
}
string source = Path.GetFullPath(options["--acd"]);
string comm = options["--comm-path"];
string operation = options.GetValueOrDefault("--operation", "mode");
string output = Path.GetFullPath(options["--out"]);
if (!Regex.IsMatch(comm, @"^Ethernet\\127\.0\.0\.[12]\\Backplane\\0$", RegexOptions.CultureInvariant))
    throw new ArgumentException("Probe accepts only Ethernet\\127.0.0.1/2\\Backplane\\0 loopback paths");
if (operation != "mode" && operation != "go-online") throw new ArgumentException("Only mode and go-online probes are supported");
if (!source.EndsWith(".ACD", StringComparison.OrdinalIgnoreCase)) throw new ArgumentException("An ACD source is required");
string folder = Path.GetDirectoryName(output)!;
Directory.CreateDirectory(folder);
string copy = Path.Combine(folder, "probe-" + Guid.NewGuid().ToString("N") + ".ACD");
string Hash(string path) => Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(path))).ToLowerInvariant();
string originalHash = Hash(source);
File.Copy(source, copy, false);
var result = new Dictionary<string,object?> {
    ["operation"] = operation, ["comm_path"] = comm, ["source_acd_sha256"] = originalHash,
    ["private_copy"] = copy, ["sdk_client_version"] = typeof(LogixProject).Assembly.GetName().Version?.ToString(),
    ["phase"] = "open", ["success"] = false, ["no_download_or_mode_change"] = true,
    ["native_online_monitoring"] = "UNVERIFIED"
};
using var cancellation = new CancellationTokenSource(TimeSpan.FromSeconds(90));
try
{
    using var project = await LogixProject.OpenLogixProjectAsync(copy, new StdOutEventLogger(), cancellation.Token);
    result["phase"] = "set-local-communications-path";
    await project.SetCommunicationsPathAsync(comm, cancellation.Token);
    result["phase"] = operation;
    if (operation == "mode") result["controller_mode"] = (await project.ReadControllerModeAsync(cancellation.Token)).ToString();
    else
    {
        await project.GoOnlineAsync(cancellation.Token);
        result["connected_state"] = (await project.ReadConnectedStateAsync(cancellation.Token)).ToString();
        await project.GoOfflineAsync(cancellation.Token);
    }
    result["success"] = true;
}
catch (Exception e)
{
    result["error_type"] = e.GetType().FullName;
    result["error"] = e.Message;
    result["hresult"] = $"0x{e.HResult:X8}";
    Console.WriteLine($"Native probe failed in {result["phase"]}: {e.Message}");
}
finally
{
    result["source_unchanged"] = Hash(source) == originalHash;
    result["private_copy_sha256_after"] = Hash(copy);
    result["utc"] = DateTimeOffset.UtcNow.ToString("O");
    File.WriteAllText(output, JsonSerializer.Serialize(result, new JsonSerializerOptions { WriteIndented = true }));
}
Console.WriteLine(JsonSerializer.Serialize(result));
return (bool)result["success"]! ? 0 : 2;
