// Offline-only rebuild; there is deliberately no communications path or Online call.
using System.Security.Cryptography;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Text.RegularExpressions;
using System.Xml;
using System.Xml.Linq;
using RockwellAutomation.LogixDesigner;
using RockwellAutomation.LogixDesigner.Logging;

if (args.Length is < 1 or > 2 || args.Length == 2 && args[1] != "--validate-request") return 2;
string requestPath = Path.GetFullPath(args[0]);
Request options;
try
{
    if (new FileInfo(requestPath).Length > 16_000_000) return 2;
    options = JsonSerializer.Deserialize<Request>(File.ReadAllText(requestPath)) ?? throw new InvalidDataException("Rebuild request is missing");
}
catch (Exception exception) { Console.Error.WriteLine(exception.Message); return 2; }
string folder = Path.GetDirectoryName(requestPath)!;
string Hash(string path) => Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(path))).ToLowerInvariant();
bool Name(string name) => Regex.IsMatch(name, "^[A-Za-z_][A-Za-z_0-9]{0,39}$");
void Inputs()
{
    if (options.InputFormat is not ("ACD" or "L5X") ||
        options.Project != Path.Combine(folder, "input." + options.InputFormat) ||
        !Regex.IsMatch(options.SourceSha256, "^[0-9a-f]{64}$") ||
        options.InputFormat == "ACD" && options.InputSha256 is not null ||
        options.InputFormat == "L5X" && (options.InputSha256 is null || !Regex.IsMatch(options.InputSha256, "^[0-9a-f]{64}$")) ||
        Hash(options.Project) != (options.InputSha256 ?? options.SourceSha256) ||
        !Regex.IsMatch(options.SourceL5xSha256, "^[0-9a-f]{64}$") || options.Programs.Length is < 1 or > 32 ||
        options.Tags.Length is < 1 or > 32 || options.Programs.Select(p => p.Name.ToLowerInvariant()).Distinct().Count() != options.Programs.Length ||
        options.Programs.Select(p => p.FileName).Distinct().Count() != options.Programs.Length)
        throw new InvalidOperationException("Rebuild source or complete plan is invalid");
    if (options.InputFormat == "L5X")
    {
        using var reader = XmlReader.Create(options.Project, new XmlReaderSettings { DtdProcessing = DtdProcessing.Prohibit, XmlResolver = null, MaxCharactersInDocument = 16000000 });
        var root = XDocument.Load(reader).Root!;
        if (root.Name != "RSLogix5000Content" || (string?)root.Attribute("TargetType") != "Controller" ||
            (string?)root.Attribute("ContainsContext") != "false" || root.Elements("Controller").Count() != 1)
            throw new InvalidOperationException("Reconstructed input must be a complete Controller L5X");
    }
    for (int i = 0; i < options.Programs.Length; i++)
    {
        var p = options.Programs[i];
        if (!Name(p.Name) || p.XPath != $"Controller/Programs/Program[@Name='{p.Name}']" || !Regex.IsMatch(p.FileName, "^uploaded-program-[0-9]{4}\\.L5X$"))
            throw new InvalidOperationException("Program path is outside the rebuild profile");
        string path = Path.Combine(folder, p.FileName);
        if (new FileInfo(path).Length > 16_000_000 || Hash(path) != p.Sha256) throw new InvalidOperationException("Program package changed");
        using var reader = XmlReader.Create(path, new XmlReaderSettings { DtdProcessing = DtdProcessing.Prohibit, XmlResolver = null, MaxCharactersInDocument = 16_000_000 });
        var root = XDocument.Load(reader).Root!;
        var targets = root.Elements("Controller").Elements("Programs").Elements("Program").ToArray();
        if (root.Name != "RSLogix5000Content" || (string?)root.Attribute("TargetType") != "Program" ||
            (string?)root.Attribute("TargetName") != p.Name || targets.Length != 1 || (string?)targets[0].Attribute("Name") != p.Name)
            throw new InvalidOperationException("Program package target is invalid");
    }
    if (options.Tags.Select(t => t.XPath).Distinct().Count() != options.Tags.Length) throw new InvalidOperationException("Duplicate tag");
    long total = 0;
    foreach (var tag in options.Tags)
    {
        if (!Regex.IsMatch(tag.XPath, "^Controller/(?:Programs/Program\\[@Name='[A-Za-z_][A-Za-z_0-9]{0,39}'\\]/)?Tags/Tag\\[@Name='[A-Za-z_][A-Za-z_0-9]{0,39}'\\]$"))
            throw new InvalidOperationException("Tag path is outside the rebuild profile");
        var bytes = Convert.FromHexString(tag.ExpectedHex); total += bytes.Length;
        if (bytes.Length is < 1 or > 32768 || total > 1024 * 1024) throw new InvalidOperationException("Tag byte extent is outside the rebuild profile");
    }
}
try { Inputs(); }
catch (Exception exception) { Console.Error.WriteLine(exception.Message); return 2; }
if (args.Length == 2) { Console.WriteLine("Rebuild request validated; no SDK project opened"); return 0; }
string acd = Path.Combine(folder, "rebuilt.ACD"), xml = Path.Combine(folder, "rebuilt.L5X");
if (File.Exists(acd) || File.Exists(xml) || File.Exists(Path.Combine(folder, "native-result.json"))) return 2;
var steps = new List<object>();
LogixProject? project = null;
bool reopened = false, cleanup = false;
string? error = null;
async Task Step(string method, Func<Task> action)
{
    Console.WriteLine(JsonSerializer.Serialize(new { method, phase = "started", time = DateTimeOffset.UtcNow })); Console.Out.Flush();
    await action(); steps.Add(new { method, status = "succeeded" });
    Console.WriteLine(JsonSerializer.Serialize(new { method, phase = "succeeded", time = DateTimeOffset.UtcNow })); Console.Out.Flush();
}
async Task Offline()
{
    if (await project!.ReadConnectedStateAsync() != LogixProject.ConnectedState.Offline) throw new InvalidOperationException("Offline required");
}
try
{
    await Step(options.InputFormat == "L5X" ? "Import assembled complete Controller L5X" : "Open bound source copy", async () => { project = await LogixProject.OpenLogixProjectAsync(options.Project, new StdOutEventLogger()); });
    await Step("Require Offline source", Offline);
    if (options.InputFormat == "ACD") foreach (var program in options.Programs)
        await Step("Import verified uploaded Program:" + program.Name, async () => {
            Inputs(); await Offline();
            await project!.PartialImportFromXmlFileAsync(program.XPath, Path.Combine(folder, program.FileName), LogixProject.ImportCollisionOptions.OverwriteOnColl);
            await Offline();
        });
    foreach (var tag in options.Tags)
        await Step("Restore uploaded value:" + tag.Name, async () => {
            await Offline(); var expected = Convert.FromHexString(tag.ExpectedHex);
            if (!tag.Constant) await project!.SetTagValueAsync(tag.XPath, LogixProject.OperationMode.Offline, expected, LogixProject.DataType.BYTE_ARRAY);
            var actual = await project!.GetTagValueAsync(tag.XPath, LogixProject.OperationMode.Offline, LogixProject.DataType.BYTE_ARRAY);
            if (!actual.ToByteArray().SequenceEqual(expected)) throw new InvalidOperationException("Rebuilt tag differs from uploaded value");
        });
    await Step("Save rebuilt ACD", () => project!.SaveAsAsync(acd, false));
    await Step("Close saved rebuilt project", () => { var closing = project!; project = null; closing.Dispose(); return Task.CompletedTask; });
    await Step("Reopen rebuilt ACD", async () => { project = await LogixProject.OpenLogixProjectAsync(acd, new StdOutEventLogger()); });
    await Step("Require reopened Offline", async () => { await Offline(); reopened = true; });
    await Step("Export reopened full Controller L5X", () => project!.SaveAsAsync(xml, false));
    await Step("Require final Offline", Offline);
    Inputs();
}
catch (Exception exception) { error = exception.ToString(); Console.WriteLine(error); }
finally
{
    try { if (project is not null) { await Offline(); project.Dispose(); project = null; } cleanup = true; }
    catch (Exception exception) { error = (error ?? "") + "\nCleanup: " + exception; }
}
bool success = error is null && reopened && cleanup;
File.WriteAllText(Path.Combine(folder, "native-result.json"), JsonSerializer.Serialize(new {
    status = success ? "succeeded" : "failed", offlineOnly = true, nativeAcdReopened = reopened,
    cleanupConfirmed = cleanup, directUploadedProjectSave = false, steps, error,
    inputFormat = options.InputFormat, inputSha256 = Hash(options.Project), uploadedCompleteL5xImported = options.InputFormat == "L5X" && reopened,
    acdSha256 = File.Exists(acd) ? Hash(acd) : null, l5xSha256 = File.Exists(xml) ? Hash(xml) : null
}, new JsonSerializerOptions { WriteIndented = true }));
return success ? 0 : 1;

sealed record Request([property: JsonPropertyName("project")] string Project,
    [property: JsonPropertyName("sourceSha256")] string SourceSha256, [property: JsonPropertyName("sourceL5xSha256")] string SourceL5xSha256,
    [property: JsonPropertyName("programs")] ProgramPackage[] Programs, [property: JsonPropertyName("tags")] TagValue[] Tags,
    [property: JsonPropertyName("inputFormat")] string InputFormat = "ACD", [property: JsonPropertyName("inputSha256")] string? InputSha256 = null);
sealed record ProgramPackage([property: JsonPropertyName("name")] string Name, [property: JsonPropertyName("xpath")] string XPath,
    [property: JsonPropertyName("fileName")] string FileName, [property: JsonPropertyName("sha256")] string Sha256);
sealed record TagValue([property: JsonPropertyName("name")] string Name, [property: JsonPropertyName("xpath")] string XPath,
    [property: JsonPropertyName("expectedHex")] string ExpectedHex, [property: JsonPropertyName("constant")] bool Constant);
