using System.Collections.Concurrent;
using System.Diagnostics;
using System.Security.Cryptography;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.Json.Serialization;
using System.Text;
using System.Text.RegularExpressions;
using System.Net.Http;
using System.Xml;
using System.Xml.Linq;
using RockwellAutomation.LogixDesigner;
using RockwellAutomation.LogixDesigner.Logging;

// Only the public SDK is used. Inputs and reports belong in private storage.
bool validateRequestOnly = args.Length == 3 && args[2] == "--validate-request";
if (args.Length != 2 && !validateRequestOnly) return 2;
var options = JsonSerializer.Deserialize<Options>(File.ReadAllText(args[0]))!;
if (options.Operation is not ("connection" or "upload" or "download" or "modes" or "edits") || options.Tags.Length > 32 ||
    options.Operation != "connection" && options.Tags.Length != 0 ||
    options.TagReadType is not ("BYTE_ARRAY" or "BOOL" or "DINT" or "REAL") ||
    options.TagReadType != "BYTE_ARRAY" && (options.Operation != "connection" || options.Tags.Length == 0))
    return 2;
string Hash() => Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(options.Project))).ToLowerInvariant();
if (Hash() != options.SourceSha256) return 2;
if (options.ControllerSourceSha256 is not null && (options.Operation != "upload" ||
    !Regex.IsMatch(options.ControllerSourceSha256, "^[0-9a-f]{64}$"))) return 2;
var controllerSourceHash = options.ControllerSourceSha256 ?? options.SourceSha256;
if ((options.ApplySupportedEdits || options.SecondEdit is not null || options.ReconnectEdits) && options.Operation != "edits" ||
    (options.SecondEdit is not null || options.ReconnectEdits) && !options.ApplySupportedEdits) return 2;
if ((options.SaveEditedAcd || options.EditTags.Length != 0) && (options.Operation != "edits" || !options.ApplySupportedEdits) ||
    options.EditTags.Length > 8 || options.EditTags.Any(tag => string.IsNullOrEmpty(tag) || tag.Length > 1024 || tag.Contains('\0'))) return 2;
if (options.Operation == "edits" && options.Edit is null) return 2;
if (options.SaveUploadedAcd && options.Operation != "upload") return 2;
if (options.ExportUploadedTags && (options.Operation != "upload" || options.UploadContent is null || options.UploadNewProject)) return 2;
if (options.SnapshotUploadedAcd && (options.Operation != "upload" || options.SaveUploadedAcd || options.UploadNewProject ||
    options.UploadContent is null || options.SnapshotBaseline is null) ||
    !options.SnapshotUploadedAcd && options.SnapshotBaseline is not null) return 2;
if (options.SaveDownloadedAcd && options.Operation != "download") return 2;
if (options.ExportDownloadedL5x && (options.Operation != "download" || !options.SaveDownloadedAcd)) return 2;
if (options.UploadNewProject && (options.Operation != "upload" || options.SaveUploadedAcd)) return 2;
if (options.UploadContent is not null && (options.Operation != "upload" || options.UploadNewProject ||
    options.UploadContent.Tags is null || options.UploadContent.Routines is null || options.UploadContent.Programs is null || options.UploadContent.SourceL5xSha256 is null ||
    options.UploadContent.Tags.Length is < 1 or > 32 || options.UploadContent.Routines.Length > 32 || options.UploadContent.Programs.Length > 32 ||
    !Regex.IsMatch(options.UploadContent.SourceL5xSha256, "^[0-9a-f]{64}$"))) return 2;
foreach (var edit in new[] { options.Edit, options.SecondEdit }.OfType<EditOptions>())
    if (edit.ImportOption is not ("LeaveEdits" or "AcceptEdits" or "FinalizeEdits") ||
        edit.ImportOption == "FinalizeEdits" && !options.ApplySupportedEdits ||
        !options.ApplySupportedEdits && (edit.InsertPosition != 0 || edit.ReplaceCount != 0) ||
        Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(edit.File))).ToLowerInvariant() != edit.Sha256 ||
        options.ApplySupportedEdits && (edit.ImportOption is not ("AcceptEdits" or "FinalizeEdits") || edit.BaseRevision is null or < 0 ||
            edit.BeforeRungs?.ValueKind != JsonValueKind.Array || edit.ExpectedRungs?.ValueKind != JsonValueKind.Array)) return 2;
if (validateRequestOnly)
{
    Console.WriteLine(JsonSerializer.Serialize(new { requestValidated = true, nativeProjectCalls = 0,
        uploadTags = options.UploadContent?.Tags.Length ?? 0, uploadRoutines = options.UploadContent?.Routines.Length ?? 0,
        uploadPrograms = options.UploadContent?.Programs.Length ?? 0, exportUploadedTags = options.ExportUploadedTags }));
    return 0;
}
var steps = new List<object>();
var logger = new Capture();
LogixProject? project = null;
bool passed = true;
bool serverFaulted = false;
bool sdkOfflineConfirmed = false;
void ObserveServerFault(Exception error)
{
    for (Exception? item = error; item is not null; item = item.InnerException)
        if (item.Message.Contains("LgxSrv_E_FATAL_ERROR", StringComparison.Ordinal) ||
            item.Message.Contains("LgxSrv_E_UNHANDLED_EXCEPTION", StringComparison.Ordinal) ||
            item.Message.Contains("LgxSrv_E_SERVER_FAULTED", StringComparison.Ordinal))
            serverFaulted = true;
}
using var http = new HttpClient(new HttpClientHandler { AllowAutoRedirect = false }) { Timeout = TimeSpan.FromSeconds(5) };
http.DefaultRequestHeaders.ConnectionClose = true;
var backendReadRecoveries = new List<object>();
object? savedEditedProject = null;
object? savedUploadedProject = null;
object? savedDownloadedProject = null;
object? uploadedContent = null;
object? savedUploadedSnapshot = null;
bool newUploadCompleted = false;
string newUploadPath = Path.Combine(Path.GetDirectoryName(Path.GetFullPath(args[1]))!, "uploaded.ACD");
if (options.UploadNewProject && File.Exists(newUploadPath)) return 2;
async Task<T> BackendRead<T>(string operation, Func<Task<T>> read)
{
    for (int attempt = 1; ; attempt++)
    {
        try { return await read(); }
        catch (HttpRequestException error) when (attempt < 3)
        {
            // Only pure backend reads use this helper. Never repeat a mode or SDK command.
            backendReadRecoveries.Add(new { operation, attempt, time = DateTimeOffset.UtcNow,
                error = error.Message, innerError = error.GetBaseException().Message });
            await Task.Delay(100);
        }
    }
}
async Task<JsonElement> Backend(string? mode = null)
{
    if (!Uri.TryCreate(options.BackendUrl, UriKind.Absolute, out var url) || url.Scheme != "http" ||
        !url.IsLoopback || !string.IsNullOrEmpty(url.UserInfo) || string.IsNullOrEmpty(options.InstanceId))
        throw new InvalidOperationException("Native diagnostic requires a pinned local emulator URL");
    var script = await BackendRead("session token", () => http.GetStringAsync(new Uri(url, "/session.js")));
    var token = JsonSerializer.Deserialize<string>(Regex.Match(script, "LOGIX_TOKEN = (\".*?\")").Groups[1].Value)!;
    async Task<JsonElement> Call(string action, object body) {
        using var request = new HttpRequestMessage(HttpMethod.Post, new Uri(url, "/api/" + action));
        request.Headers.Add("X-Logix-Token", token);
        request.Content = new StringContent(JsonSerializer.Serialize(body), Encoding.UTF8, "application/json");
        using var response = await http.SendAsync(request);
        response.EnsureSuccessStatusCode();
        var state = JsonDocument.Parse(await response.Content.ReadAsStringAsync()).RootElement.Clone();
        if (state.GetProperty("instance_id").GetString() != options.InstanceId ||
            state.GetProperty("connectivity").GetProperty("native_correlation").GetProperty("source_acd_sha256").GetString() != controllerSourceHash)
            throw new InvalidOperationException("Emulator instance/source changed");
        return state;
    }
    var current = await BackendRead("observe", () => Call("observe", new {}));
    return mode is null ? current : await Call("controller-mode", new { mode });
}
async Task CaptureProtocolTrace(string fileName, string operation = "edit")
{
    await Step("Capture " + operation + " protocol checkpoint:" + fileName, async () => {
        await Backend(); // Pin instance and source on both sides of this trace read.
        var url = new Uri(options.BackendUrl!);
        var script = await BackendRead("edit trace token", () => http.GetStringAsync(new Uri(url, "/session.js")));
        var token = JsonSerializer.Deserialize<string>(Regex.Match(script, "LOGIX_TOKEN = (\".*?\")").Groups[1].Value)!;
        var text = await BackendRead("edit trace:" + fileName, async () => {
            // Trace retrieval is a pure read. Recreate its HTTP request on each
            // transport retry; the SDK import itself is never repeated here.
            using var request = new HttpRequestMessage(HttpMethod.Post, new Uri(url, "/api/connectivity-trace"));
            request.Headers.Add("X-Logix-Token", token);
            request.Content = new StringContent("{}", Encoding.UTF8, "application/json");
            using var response = await http.SendAsync(request);
            response.EnsureSuccessStatusCode();
            return await response.Content.ReadAsStringAsync();
        });
        var trace = JsonDocument.Parse(text).RootElement;
        if (trace.GetProperty("native_correlation").GetProperty("source_acd_sha256").GetString() != controllerSourceHash)
            throw new InvalidOperationException("Protocol trace source changed");
        await Backend();
        await File.WriteAllTextAsync(Path.Combine(Path.GetDirectoryName(Path.GetFullPath(args[1]))!, fileName), text);
        return true;
    });
}
async Task SaveEditedAcd()
{
    var directory = Path.GetDirectoryName(Path.GetFullPath(args[1]))!;
    var xmlPath = Path.Combine(directory, "emulator-edited.L5X");
    var acdPath = Path.Combine(directory, "edited.ACD");
    var reopenedPath = Path.Combine(directory, "reopened.L5X");
    if (new[] { xmlPath, acdPath, reopenedPath }.Any(File.Exists))
        throw new InvalidOperationException("Edited-project outputs must be new files");
    var before = await Backend();
    if (before.GetProperty("controller").GetProperty("mode").GetString() != "Program" ||
        before.GetProperty("connectivity").GetProperty("native_programming_lease").GetProperty("owned").GetBoolean())
        throw new InvalidOperationException("Finish the native transaction in Program before saving");
    var url = new Uri(options.BackendUrl!);
    var script = await BackendRead("export token", () => http.GetStringAsync(new Uri(url, "/session.js")));
    var token = JsonSerializer.Deserialize<string>(Regex.Match(script, "LOGIX_TOKEN = (\".*?\")").Groups[1].Value)!;
    var text = await BackendRead("export edited L5X", async () => {
        using var request = new HttpRequestMessage(HttpMethod.Post, new Uri(url, "/api/export-edited-l5x"));
        request.Headers.Add("X-Logix-Token", token);
        request.Content = new StringContent("{}", Encoding.UTF8, "application/json");
        using var response = await http.SendAsync(request);
        response.EnsureSuccessStatusCode();
        return await response.Content.ReadAsStringAsync();
    });
    var export = JsonDocument.Parse(text).RootElement;
    var payload = Encoding.UTF8.GetBytes(export.GetProperty("content").GetString()!);
    string HashFile(string path) => Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(path))).ToLowerInvariant();
    var xmlHash = Convert.ToHexString(SHA256.HashData(payload)).ToLowerInvariant();
    if (xmlHash != export.GetProperty("sha256").GetString() || export.GetProperty("native_acd_correlation").GetBoolean() ||
        export.GetProperty("base_l5x_sha256").GetString() != before.GetProperty("connectivity").GetProperty("source_l5x_sha256").GetString() ||
        export.GetProperty("logic_revision").GetInt64() != before.GetProperty("routine_edits").GetProperty("revision").GetInt64() ||
        export.GetProperty("logic_sha256").GetString() != before.GetProperty("routine_edits").GetProperty("logic_sha256").GetString())
        throw new InvalidOperationException("Edited L5X does not match the pinned active logic");
    CheckPreserved(before, await Backend(), true);
    using (var file = new FileStream(xmlPath, FileMode.CreateNew, FileAccess.Write)) await file.WriteAsync(payload);
    async Task Close(string name) => await Step(name, () => {
        var closing = project!; project = null; closing.Dispose(); return Task.FromResult<object?>(true);
    });
    await Close("Close original SDK project before L5X import");
    await Step("OpenLogixProjectAsync:emulator-edited.L5X", async () => {
        project = await LogixProject.OpenLogixProjectAsync(xmlPath, logger); return true;
    });
    await Step("Verify imported L5X is Offline", async () => {
        if (await project!.ReadConnectedStateAsync() != LogixProject.ConnectedState.Offline)
            throw new InvalidOperationException("Imported L5X unexpectedly connected");
        return true;
    });
    await Step("SaveAsAsync:edited.ACD", async () => { await project!.SaveAsAsync(acdPath, false); return true; });
    await Close("Close imported L5X before ACD reopen");
    await Step("OpenLogixProjectAsync:edited.ACD", async () => {
        project = await LogixProject.OpenLogixProjectAsync(acdPath, logger); return true;
    });
    await Step("Verify reopened edited ACD is Offline", async () => {
        if (await project!.ReadConnectedStateAsync() != LogixProject.ConnectedState.Offline)
            throw new InvalidOperationException("Reopened ACD unexpectedly connected");
        return true;
    });
    await Step("SaveAsAsync:reopened.L5X", async () => { await project!.SaveAsAsync(reopenedPath, false); return true; });
    if (HashFile(xmlPath) != xmlHash || new FileInfo(acdPath).Length == 0 || new FileInfo(reopenedPath).Length == 0)
        throw new InvalidOperationException("Native save changed its input or produced an empty file");
    CheckPreserved(before, await Backend(), true);
    savedEditedProject = new { inputL5xSha256 = xmlHash, acdSha256 = HashFile(acdPath),
        reopenedL5xSha256 = HashFile(reopenedPath), nativeAcdReopened = true, offlineOnly = true };
}
async Task SaveDownloadedAcd()
{
    var acdPath = Path.Combine(Path.GetDirectoryName(Path.GetFullPath(args[1]))!, "downloaded.ACD");
    var xmlPath = Path.Combine(Path.GetDirectoryName(acdPath)!, "downloaded.L5X");
    string? exportedHash = null;
    if (File.Exists(acdPath)) throw new InvalidOperationException("Downloaded-project output must be a new file");
    if (options.ExportDownloadedL5x && File.Exists(xmlPath)) throw new InvalidOperationException("Downloaded-content output must be a new file");
    var before = await Backend();
    if (before.GetProperty("connectivity").GetProperty("native_download").ValueKind != JsonValueKind.Object ||
        !before.GetProperty("connectivity").GetProperty("native_download").GetProperty("source_equivalent").GetBoolean())
        throw new InvalidOperationException("Source-equivalent installation must finish before saving");
    await Step("ReadConnectedStateAsync:before-download-save", async () => {
        var state = await project!.ReadConnectedStateAsync();
        if (state != LogixProject.ConnectedState.Offline) throw new InvalidOperationException("Offline required before saving");
        return state.ToString();
    });
    await Step("SaveAsAsync:downloaded.ACD", async () => { await project!.SaveAsAsync(acdPath, false); return true; });
    await Step("Close downloaded SDK project", () => {
        var closing = project!; project = null; closing.Dispose(); return Task.FromResult<object?>(true);
    });
    await Step("OpenLogixProjectAsync:downloaded.ACD", async () => {
        project = await LogixProject.OpenLogixProjectAsync(acdPath, logger); return true;
    });
    if (options.ExportDownloadedL5x)
    {
        await Step("Require reopened downloaded project Offline", async () => {
            if (await project!.ReadConnectedStateAsync() != LogixProject.ConnectedState.Offline) throw new InvalidOperationException("Offline content export required");
            return true;
        });
        await Step("SaveAsAsync:downloaded.L5X", async () => { await project!.SaveAsAsync(xmlPath, false); return true; });
        exportedHash = Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(xmlPath))).ToLowerInvariant();
    }
    await Step("SetCommunicationsPathAsync:downloaded.ACD", async () => {
        await project!.SetCommunicationsPathAsync(options.CommunicationsPath); return true;
    });
    await Step("GoOnlineAsync:downloaded.ACD", async () => { await project!.GoOnlineAsync(); return true; });
    await Step("ReadConnectedStateAsync:downloaded.ACD", async () => {
        var state = await project!.ReadConnectedStateAsync();
        if (state != LogixProject.ConnectedState.Online) throw new InvalidOperationException("Reopened downloaded ACD is not Online");
        return state.ToString();
    });
    CheckPreserved(before, await Backend(), true);
    savedDownloadedProject = new {
        acdSha256 = Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(acdPath))).ToLowerInvariant(),
        nativeAcdReopened = true, reopenedOnline = true, downloadResultSaved = true,
        offlineContentExported = options.ExportDownloadedL5x, reopenedL5xSha256 = exportedHash,
        emulatorPersistence = "memory_only", nativeControllerEquivalence = "NOT ASSESSED"
    };
}

async Task SaveUploadedAcd()
{
    var directory = Path.GetDirectoryName(Path.GetFullPath(args[1]))!;
    var acdPath = Path.Combine(directory, "uploaded.ACD");
    var xmlPath = Path.Combine(directory, "uploaded.L5X");
    if (new[] { acdPath, xmlPath }.Any(File.Exists))
        throw new InvalidOperationException("Uploaded-project outputs must be new files");
    var before = await Backend();
    if (await project!.ReadConnectedStateAsync() != LogixProject.ConnectedState.Offline)
        await Step("GoOfflineAsync:before-upload-save", async () => { await project!.GoOfflineAsync(); return true; });
    await Step("Verify uploaded project is Offline before saving", async () => {
        if (await project!.ReadConnectedStateAsync() != LogixProject.ConnectedState.Offline)
            throw new InvalidOperationException("Upload must be Offline before saving");
        return true;
    });
    await Step("SaveAsAsync:uploaded.ACD", async () => { await project!.SaveAsAsync(acdPath, false); return true; });
    await Step("Close uploaded project before ACD reopen", () => {
        var closing = project!; project = null; closing.Dispose(); return Task.FromResult<object?>(true);
    });
    await Step("OpenLogixProjectAsync:uploaded.ACD", async () => {
        project = await LogixProject.OpenLogixProjectAsync(acdPath, logger); return true;
    });
    await Step("Verify reopened uploaded ACD is Offline", async () => {
        if (await project!.ReadConnectedStateAsync() != LogixProject.ConnectedState.Offline)
            throw new InvalidOperationException("Reopened uploaded ACD unexpectedly connected");
        return true;
    });
    await Step("SaveAsAsync:uploaded.L5X", async () => { await project!.SaveAsAsync(xmlPath, false); return true; });
    if (new FileInfo(acdPath).Length == 0 || new FileInfo(xmlPath).Length == 0)
        throw new InvalidOperationException("Uploaded save produced an empty file");
    CheckPreserved(before, await Backend(), true);
    string HashFile(string path) => Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(path))).ToLowerInvariant();
    savedUploadedProject = new { acdSha256 = HashFile(acdPath), reopenedL5xSha256 = HashFile(xmlPath),
        nativeAcdReopened = true, offlineOnly = true, uploadResultSaved = true };
}
string CanonicalRung(string text)
{
    // Neutral source may differ in whitespace outside literal operands. Keep
    // every literal character; Python separately parses the exported rungs.
    var output = new StringBuilder(); char quote = '\0'; bool escape = false;
    foreach (char c in text)
    {
        if (quote != '\0')
        {
            output.Append(c);
            if (escape) escape = false;
            else if (c == '\\') escape = true;
            else if (c == quote) quote = '\0';
        }
        else if (c is '\'' or '"') { quote = c; output.Append(c); }
        else if (!char.IsWhiteSpace(c)) output.Append(c);
    }
    if (quote != '\0') throw new InvalidOperationException("Unterminated exported rung literal");
    return output.ToString().TrimEnd(';');
}
int CheckRoutineExport(string path, UploadRoutine routine)
{
    if (new FileInfo(path).Length is < 8 or > 16000000) throw new InvalidOperationException("Native routine export outside bounds");
    var settings = new XmlReaderSettings { DtdProcessing = DtdProcessing.Prohibit, XmlResolver = null, MaxCharactersInDocument = 16000000 };
    using var reader = XmlReader.Create(path, settings); var root = XDocument.Load(reader).Root!;
    if (root.Name != "RSLogix5000Content" || (string?)root.Attribute("TargetType") != "Routine" ||
        (string?)root.Attribute("TargetName") != routine.Name) throw new InvalidOperationException("Native routine export target differs");
    var program = root.Elements("Controller").Single().Element("Programs")!.Elements("Program")
        .Single(node => (string?)node.Attribute("Name") == routine.Program);
    var target = program.Element("Routines")!.Elements("Routine").Single(node => (string?)node.Attribute("Name") == routine.Name);
    if ((string?)target.Attribute("Type") != "RLL") throw new InvalidOperationException("Native routine export is not RLL");
    var rungs = target.Elements("RLLContent").Single().Elements().Select(node => {
        if (node.Name != "Rung" || (string?)node.Attribute("Type") is not (null or "N")) throw new InvalidOperationException("Unexpected native RLL content");
        return CanonicalRung(node.Elements("Text").Single().Value);
    }).ToArray();
    if (!rungs.SequenceEqual(routine.ExpectedRungs.Select(CanonicalRung)))
        throw new InvalidOperationException("Native routine differs from unchanged source logic");
    return rungs.Length;
}
async Task VerifyUploadedContent()
{
    var expected = options.UploadContent!; var before = await Backend();
    if (before.GetProperty("connectivity").GetProperty("source_l5x_sha256").GetString() != expected.SourceL5xSha256)
        throw new InvalidOperationException("Uploaded-content source binding changed");
    await Step("Verify uploaded content is Offline", async () => {
        if (await project!.ReadConnectedStateAsync() != LogixProject.ConnectedState.Offline)
            throw new InvalidOperationException("Uploaded-content reads require Offline");
        return true;
    });
    var tags = new List<object>(); var routines = new List<object>(); var programs = new List<object>();
    object? controllerTags = null;
    // Retain partial evidence if a later read/export fails. Completeness and
    // actual contents are independently checked by the Python receipt reader.
    uploadedContent = new { sourceL5xSha256 = expected.SourceL5xSha256, offlineOnly = true, tags, routines, programs, controllerTags };
    foreach (var tag in expected.Tags)
    {
        if (!Regex.IsMatch(tag.ExpectedHex, "^(?:[0-9a-f]{2}){1,32768}$") ||
            !Regex.IsMatch(tag.XPath, @"^Controller/(?:Programs/Program\[@Name='[A-Za-z_][A-Za-z_0-9]{0,39}'\]/)?Tags/Tag\[@Name='[A-Za-z_][A-Za-z_0-9]{0,39}'\]$"))
            throw new InvalidOperationException("Invalid uploaded-content tag plan");
        await Step("Uploaded offline tag:" + tag.Name, async () => {
            var value = await project!.GetTagValueAsync(tag.XPath, LogixProject.OperationMode.Offline, LogixProject.DataType.BYTE_ARRAY);
            string actual = Convert.ToHexString(value.ToByteArray()).ToLowerInvariant();
            tags.Add(new { name = tag.Name, xpath = tag.XPath, actualHex = actual });
            if (actual != tag.ExpectedHex) throw new InvalidOperationException("Uploaded offline tag differs from current emulator value: " + tag.Name);
            return new { bytes = value.Length, matchesCurrentModel = true };
        });
    }
    var directory = Path.GetDirectoryName(Path.GetFullPath(args[1]))!;
    foreach (var routine in expected.Routines)
    {
        string path = Path.Combine(directory, routine.FileName);
        string xpath = $"Controller/Programs/Program[@Name='{routine.Program}']/Routines/Routine[@Name='{routine.Name}']";
        if (!Regex.IsMatch(routine.FileName, "^uploaded-routine-[0-9]{4}\\.L5X$") || File.Exists(path) ||
            !Regex.IsMatch(routine.Program, "^[A-Za-z_][A-Za-z_0-9]{0,39}$") ||
            !Regex.IsMatch(routine.Name, "^[A-Za-z_][A-Za-z_0-9]{0,39}$") || routine.XPath != xpath ||
            routine.ExpectedRungs.Length > 10000 || routine.ExpectedRungs.Any(text => text.Length > 65536))
            throw new InvalidOperationException("Invalid uploaded-content routine plan");
        await Step("PartialExportToXmlFileAsync:uploaded:" + routine.Program + "/" + routine.Name, async () => {
            await project!.PartialExportToXmlFileAsync(xpath, path);
            int rungs = CheckRoutineExport(path, routine);
            routines.Add(new { fileName = routine.FileName, sha256 = Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(path))).ToLowerInvariant() });
            return new { rungs, matchesSource = true };
        });
    }
    foreach (var program in expected.Programs)
    {
        string path = Path.Combine(directory, program.FileName);
        string xpath = $"Controller/Programs/Program[@Name='{program.Name}']";
        if (!Regex.IsMatch(program.Name, "^[A-Za-z_][A-Za-z_0-9]{0,39}$") || program.XPath != xpath ||
            !Regex.IsMatch(program.FileName, "^uploaded-program-[0-9]{4}\\.L5X$") || File.Exists(path))
            throw new InvalidOperationException("Invalid uploaded-content Program plan");
        await Step("PartialExportToXmlFileAsync:uploaded-program:" + program.Name, async () => {
            await project!.PartialExportToXmlFileAsync(xpath, path);
            if (new FileInfo(path).Length is < 8 or > 16000000) throw new InvalidOperationException("Native Program export outside bounds");
            var settings = new XmlReaderSettings { DtdProcessing = DtdProcessing.Prohibit, XmlResolver = null, MaxCharactersInDocument = 16000000 };
            using var reader = XmlReader.Create(path, settings); var root = XDocument.Load(reader).Root!;
            if (root.Name != "RSLogix5000Content" || (string?)root.Attribute("TargetType") != "Program" ||
                (string?)root.Attribute("TargetName") != program.Name) throw new InvalidOperationException("Native Program export target differs");
            programs.Add(new { fileName = program.FileName, sha256 = Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(path))).ToLowerInvariant() });
            return new { exported = true, offlineOnly = true };
        });
    }
    if (options.ExportUploadedTags)
        await Step("PartialExportToXmlFileAsync:uploaded-controller-tags", async () => {
            const string fileName = "uploaded-controller-tags.L5X";
            string path = Path.Combine(directory, fileName);
            if (File.Exists(path)) throw new InvalidOperationException("Controller-tag export must be a new file");
            await project!.PartialExportToXmlFileAsync("Controller/Tags/Tag", path);
            if (new FileInfo(path).Length is < 8 or > 16000000) throw new InvalidOperationException("Native controller-tag export outside bounds");
            controllerTags = new { fileName, sha256 = Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(path))).ToLowerInvariant() };
            return new { exported = true, offlineOnly = true };
        });
    if (await project!.ReadConnectedStateAsync() != LogixProject.ConnectedState.Offline)
        throw new InvalidOperationException("Uploaded-content export unexpectedly connected");
    CheckPreserved(before, await Backend(), true);
    uploadedContent = new { sourceL5xSha256 = expected.SourceL5xSha256, offlineOnly = true, tags, routines, programs, controllerTags };
}
async Task SaveUploadedSnapshot()
{
    string directory = Path.GetDirectoryName(Path.GetFullPath(args[1]))!;
    string baseline = Path.GetFullPath(options.SnapshotBaseline!);
    string acdPath = Path.Combine(directory, "snapshot.ACD"), xmlPath = Path.Combine(directory, "snapshot.L5X");
    string HashFile(string path) => Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(path))).ToLowerInvariant();
    if (baseline != Path.Combine(directory, "snapshot-input.ACD") || HashFile(baseline) != options.SourceSha256 ||
        File.Exists(acdPath) || File.Exists(xmlPath)) throw new InvalidOperationException("Snapshot baseline or fresh outputs changed");
    var before = await Backend();
    await Step("Close verified uploaded project before value snapshot", () => {
        var closing = project!; project = null; closing.Dispose(); return Task.FromResult<object?>(true);
    });
    await Step("OpenLogixProjectAsync:snapshot-baseline", async () => {
        project = await LogixProject.OpenLogixProjectAsync(baseline, logger); return true;
    });
    await Step("Require Offline snapshot baseline", async () => {
        if (await project!.ReadConnectedStateAsync() != LogixProject.ConnectedState.Offline) throw new InvalidOperationException("Offline required");
        return true;
    });
    foreach (var routine in options.UploadContent!.Routines)
    {
        string path = Path.Combine(directory, routine.FileName.Replace("uploaded-routine-", "baseline-routine-"));
        if (File.Exists(path)) throw new InvalidOperationException("Baseline source export must be fresh");
        await Step("Verify snapshot baseline routine:" + routine.Program + "/" + routine.Name, async () => {
            await project!.PartialExportToXmlFileAsync(routine.XPath, path); return CheckRoutineExport(path, routine);
        });
    }
    foreach (var tag in options.UploadContent.Tags)
        await Step("Snapshot Offline tag:" + tag.Name, async () => {
            var raw = Convert.FromHexString(tag.ExpectedHex);
            if (!tag.Constant) await project!.SetTagValueAsync(tag.XPath, LogixProject.OperationMode.Offline, raw, LogixProject.DataType.BYTE_ARRAY);
            var value = await project!.GetTagValueAsync(tag.XPath, LogixProject.OperationMode.Offline, LogixProject.DataType.BYTE_ARRAY);
            if (!value.ToByteArray().SequenceEqual(raw)) throw new InvalidOperationException("Snapshot Offline value differs from uploaded value");
            return new { bytes = raw.Length, matchesUploadedValue = true };
        });
    await Step("SaveAsAsync:snapshot.ACD", async () => { await project!.SaveAsAsync(acdPath, false); return true; });
    await Step("Close saved value snapshot", () => {
        var closing = project!; project = null; closing.Dispose(); return Task.FromResult<object?>(true);
    });
    await Step("OpenLogixProjectAsync:snapshot.ACD", async () => {
        project = await LogixProject.OpenLogixProjectAsync(acdPath, logger); return true;
    });
    await Step("Require reopened snapshot Offline", async () => {
        if (await project!.ReadConnectedStateAsync() != LogixProject.ConnectedState.Offline) throw new InvalidOperationException("Offline required");
        return true;
    });
    await Step("SaveAsAsync:snapshot.L5X", async () => { await project!.SaveAsAsync(xmlPath, false); return true; });
    await Step("SetCommunicationsPathAsync:snapshot.ACD", async () => { await project!.SetCommunicationsPathAsync(options.CommunicationsPath); return true; });
    await Step("GoOnlineAsync:snapshot.ACD", async () => { await project!.GoOnlineAsync(); return true; });
    await Step("Verify reopened snapshot Online", async () => {
        if (await project!.ReadConnectedStateAsync() != LogixProject.ConnectedState.Online) throw new InvalidOperationException("Snapshot is not Online");
        return true;
    });
    await Step("CheckMode:snapshot.ACD", async () => { await CheckMode("Program"); return true; });
    foreach (var tag in options.UploadContent.Tags.Where(tag => !tag.Constant && tag.TypeCode == 0xC4 &&
            tag.ExpectedHex.Length == 8 && tag.Dimensions?.All(size => size == 0) == true))
        await Step("Snapshot Online DINT:" + tag.Name, async () => {
            int value = await project!.GetTagValueDINTAsync(tag.XPath, LogixProject.OperationMode.Online);
            if (value != System.Buffers.Binary.BinaryPrimitives.ReadInt32LittleEndian(Convert.FromHexString(tag.ExpectedHex)))
                throw new InvalidOperationException("Snapshot Online value differs from uploaded value");
            return value;
        });
    foreach (var tag in options.UploadContent.Tags.Where(tag => !tag.Constant && tag.TypeCode == 0xC1 &&
            tag.ExpectedHex is "00" or "01" && tag.Dimensions?.All(size => size == 0) == true))
        await Step("Snapshot Online BOOL:" + tag.Name, async () => {
            bool value = await project!.GetTagValueBOOLAsync(tag.XPath, LogixProject.OperationMode.Online);
            if (value != (tag.ExpectedHex == "01")) throw new InvalidOperationException("Snapshot Online BOOL differs from uploaded value");
            return value;
        });
    CheckPreserved(before, await Backend(), true);
    await Step("GoOfflineAsync:snapshot.ACD", async () => { await project!.GoOfflineAsync(); return true; });
    await Step("Require snapshot Offline after Online check", async () => {
        if (await project!.ReadConnectedStateAsync() != LogixProject.ConnectedState.Offline) throw new InvalidOperationException("Offline required");
        return true;
    });
    if (HashFile(baseline) != options.SourceSha256) throw new InvalidOperationException("Snapshot baseline changed");
    savedUploadedSnapshot = new { sourceEquivalentValueSnapshot = true, baselineLogicVerified = true,
        baselineSha256 = options.SourceSha256, acdSha256 = HashFile(acdPath), reopenedL5xSha256 = HashFile(xmlPath),
        nativeAcdReopened = true, reopenedOnline = true };
}
bool Same(JsonElement left, JsonElement right) => JsonNode.DeepEquals(JsonNode.Parse(left.GetRawText()), JsonNode.Parse(right.GetRawText()));
async Task SaveState(string fileName, JsonElement state) => await File.WriteAllTextAsync(
    Path.Combine(Path.GetDirectoryName(Path.GetFullPath(args[1]))!, fileName), state.GetRawText());
void CheckEditState(JsonElement state, EditOptions edit, bool applied)
{
    var names = Regex.Matches(edit.XPath, "@Name='([^']+)'").Select(match => match.Groups[1].Value).ToArray();
    if (names.Length != 2) throw new InvalidOperationException("Expected one ordinary program/routine path");
    var key = string.Join("/", names);
    var routine = state.GetProperty("routines").EnumerateArray().Single(item => item.GetProperty("key").GetString() == key);
    var nodes = JsonSerializer.SerializeToElement(routine.GetProperty("rungs").EnumerateArray().Select(rung => rung.GetProperty("nodes")));
    if (!Same(nodes, (applied ? edit.ExpectedRungs : edit.BeforeRungs)!.Value) ||
        state.GetProperty("routine_edits").GetProperty("revision").GetInt64() != edit.BaseRevision + (applied ? 1 : 0) ||
        state.GetProperty("controller").GetProperty("mode").GetString() != "Program" || state.GetProperty("controller").GetProperty("running").GetBoolean())
        throw new InvalidOperationException("Active routine/revision does not match the exact generated insert");
}
void CheckPreserved(JsonElement before, JsonElement after, bool includeLogic, string? editedPath = null)
{
    var fields = new[] { "instance_id", "tags", "scan", "ms", "changes", "mode", "tasks", "entry_routines", "controller" };
    foreach (var field in includeLogic ? fields.Concat(new[] { "routines", "routine_edits" }) : fields)
        if (!Same(before.GetProperty(field), after.GetProperty(field)))
            throw new InvalidOperationException("Unexpected model change: " + field);
    if (!includeLogic)
    {
        var key = string.Join("/", Regex.Matches(editedPath!, "@Name='([^']+)'").Select(match => match.Groups[1].Value));
        JsonElement Others(JsonElement state) => JsonSerializer.SerializeToElement(state.GetProperty("routines").EnumerateArray()
            .Where(routine => routine.GetProperty("key").GetString() != key));
        if (!Same(Others(before), Others(after))) throw new InvalidOperationException("An unrelated routine changed");
    }
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
    var startedAt = DateTimeOffset.UtcNow;
    // Keep the last entered/completed SDK step if the native process stalls.
    // These private diagnostic lines never substitute for sdk-result.json.
    void Progress(string phase) {
        Console.WriteLine(JsonSerializer.Serialize(new { kind = "native_step", method = name,
            phase, startedAt, time = DateTimeOffset.UtcNow, elapsedMs = clock.Elapsed.TotalMilliseconds }));
        Console.Out.Flush();
    }
    Progress("started");
    try
    {
        var value = await action();
        steps.Add(new { method = name, status = "succeeded", value, startedAt, finishedAt = DateTimeOffset.UtcNow,
                        elapsedMs = clock.Elapsed.TotalMilliseconds });
        Progress("succeeded");
    }
    catch (Exception error)
    {
        passed = false;
        ObserveServerFault(error);
        var chain = new List<object>();
        for (Exception? item = error; item is not null && chain.Count < 16; item = item.InnerException)
            chain.Add(new { type = item.GetType().FullName, message = item.Message, hresult = $"0x{item.HResult:X8}" });
        steps.Add(new { method = name, status = "failed", errors = chain, startedAt, finishedAt = DateTimeOffset.UtcNow,
                        elapsedMs = clock.Elapsed.TotalMilliseconds });
        Progress("failed");
        throw;
    }
}
try
{
    if (!options.UploadNewProject)
    {
    await Step("OpenLogixProjectAsync", async () => {
        project = await LogixProject.OpenLogixProjectAsync(options.Project, logger); return true;
    });
    await Step("SetCommunicationsPathAsync", async () => {
        await project!.SetCommunicationsPathAsync(options.CommunicationsPath); return true;
    });
    await Step("ReadConnectedStateAsync:initial", async () => (await project!.ReadConnectedStateAsync()).ToString());
    if (options.SnapshotUploadedAcd)
    {
        await Step("GoOnlineAsync:verify-snapshot-baseline", async () => { await project!.GoOnlineAsync(); return true; });
        await Step("Verify snapshot baseline Online", async () => {
            if (await project!.ReadConnectedStateAsync() != LogixProject.ConnectedState.Online) throw new InvalidOperationException("Baseline is not Online");
            return true;
        });
        await Step("GoOfflineAsync:verify-snapshot-baseline", async () => { await project!.GoOfflineAsync(); return true; });
        await Step("Require snapshot baseline Offline before upload", async () => {
            if (await project!.ReadConnectedStateAsync() != LogixProject.ConnectedState.Offline) throw new InvalidOperationException("Offline required");
            return true;
        });
    }
    }
    if (options.Operation is "upload" or "download")
    {
        await CaptureProtocolTrace("before-transfer-trace.json", options.Operation);
        try
        {
            if (options.UploadNewProject)
                await Step("UploadToNewProjectAsync", async () => {
                    project = await LogixProject.UploadToNewProjectAsync(newUploadPath, options.CommunicationsPath, logger);
                    newUploadCompleted = true;
                    return true;
                });
            else if (options.Operation == "upload")
                await Step("UploadAsync", async () => { await project!.UploadAsync(); return true; });
            else
                await Step("DownloadAsync", async () => { await project!.DownloadAsync(); return true; });
        }
        finally { await CaptureProtocolTrace("after-transfer-trace.json", options.Operation); }
        if (options.UploadContent is not null) await VerifyUploadedContent();
        if (options.SaveUploadedAcd) await SaveUploadedAcd();
        if (options.SnapshotUploadedAcd) await SaveUploadedSnapshot();
        if (options.SaveDownloadedAcd) await SaveDownloadedAcd();
    }
    else
    {
        await Step("GoOnlineAsync", async () => { await project!.GoOnlineAsync(); return true; });
        await Step("ReadConnectedStateAsync:online", async () => {
            var state = await project!.ReadConnectedStateAsync();
            if (state != LogixProject.ConnectedState.Online) throw new InvalidOperationException("SDK did not report Online");
            return state.ToString();
        });
        await Step("ReadControllerModeAsync", async () => (await project!.ReadControllerModeAsync()).ToString());
        if (options.Operation == "edits")
        {
            await Step("Verify explicit controller edit access", async () => {
                var state = await Backend();
                var controller = state.GetProperty("controller");
                if (controller.GetProperty("mode").GetString() != "Program" || controller.GetProperty("running").GetBoolean() ||
                    state.GetProperty("connectivity").GetProperty("native_programming_lease").GetProperty("online_edits").GetBoolean() != options.ApplySupportedEdits)
                    throw new InvalidOperationException("Edit access does not match the explicit supported-edit option");
                await CheckMode("Program");
                return true;
            });
            int editIndex = 0;
            foreach (var edit in new[] { options.Edit, options.SecondEdit }.OfType<EditOptions>())
            {
                editIndex++;
                string suffix = editIndex == 1 ? "edit" : "edit2";
                var beforeEdit = await Backend();
                if (options.ApplySupportedEdits)
                    await Step("Verify edit base:" + editIndex, () => {
                        CheckEditState(beforeEdit, edit, false); return Task.FromResult<object?>(true);
                    });
                await SaveState("before-" + suffix + "-state.json", beforeEdit);
                await CaptureProtocolTrace("before-" + suffix + "-trace.json");
                try
                {
                    await Step("PartialImportRungsFromXmlFileAsync:" + edit.ImportOption + (editIndex == 1 ? "" : ":2"), async () => {
                        var option = edit.ImportOption switch {
                            "LeaveEdits" => LogixProject.PartialImportOption.LeaveEdits,
                            "FinalizeEdits" => LogixProject.PartialImportOption.FinalizeEdits,
                            _ => LogixProject.PartialImportOption.AcceptEdits
                        };
                        await project!.PartialImportRungsFromXmlFileAsync(edit.XPath, edit.InsertPosition, edit.ReplaceCount, edit.File, option);
                        return new { importOption = edit.ImportOption, activeControllerEdits = "NOT ASSESSED" };
                    });
                }
                finally { await CaptureProtocolTrace("after-" + suffix + "-trace.json"); }
                var afterEdit = await Backend();
                await SaveState("after-" + suffix + "-state.json", afterEdit);
                if (options.ApplySupportedEdits)
                    await Step("Verify applied routine:" + editIndex, () => {
                        CheckEditState(afterEdit, edit, true); CheckPreserved(beforeEdit, afterEdit, false, edit.XPath);
                        return Task.FromResult<object?>(true);
                    });
                if (options.ReconnectEdits)
                {
                    await Step("GoOfflineAsync:edit" + editIndex, async () => { await project!.GoOfflineAsync(); return true; });
                    await Step("ReadConnectedStateAsync:edit" + editIndex, async () => {
                        var state = await project!.ReadConnectedStateAsync();
                        if (state != LogixProject.ConnectedState.Offline) throw new InvalidOperationException("SDK did not report Offline between edits");
                        return state.ToString();
                    });
                    await Step("GoOnlineAsync:edit" + editIndex, async () => { await project!.GoOnlineAsync(); return true; });
                    await Step("Verify reconnected edited project:" + editIndex, async () => {
                        if (await project!.ReadConnectedStateAsync() != LogixProject.ConnectedState.Online)
                            throw new InvalidOperationException("SDK did not report Online after edit");
                        await CheckMode("Program");
                        var connected = await Backend();
                        await SaveState("after-reconnect-" + editIndex + "-state.json", connected);
                        CheckEditState(connected, edit, true); CheckPreserved(afterEdit, connected, true);
                        return true;
                    });
                }
            }
            foreach (var tag in options.EditTags)
            {
                if (serverFaulted) break;
                try { await Step("Post-edit GetTagValueDINTAsync:" + tag, async () =>
                    await project!.GetTagValueDINTAsync(tag, LogixProject.OperationMode.Online)); }
                catch { }
            }
        }
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
        {
            if (serverFaulted) break;
            string method = options.TagReadType switch {
                "BOOL" => "GetTagValueBOOLAsync", "DINT" => "GetTagValueDINTAsync",
                "REAL" => "GetTagValueREALAsync", _ => "GetTagValueAsync" };
            try { await Step(method + ":" + tag, async () => {
                if (options.TagReadType == "BOOL") return await project!.GetTagValueBOOLAsync(tag, LogixProject.OperationMode.Online);
                if (options.TagReadType == "DINT") return await project!.GetTagValueDINTAsync(tag, LogixProject.OperationMode.Online);
                if (options.TagReadType == "REAL") return await project!.GetTagValueREALAsync(tag, LogixProject.OperationMode.Online);
                return (await project!.GetTagValueAsync(tag, LogixProject.OperationMode.Online, LogixProject.DataType.BYTE_ARRAY)).ToBase64();
            }); }
            catch { }
        }
        if (!serverFaulted)
        {
            await Step("GoOfflineAsync", async () => { await project!.GoOfflineAsync(); return true; });
            await Step("ReadConnectedStateAsync:final", async () => {
                var state = await project!.ReadConnectedStateAsync();
                if (state != LogixProject.ConnectedState.Offline) throw new InvalidOperationException("SDK did not report Offline");
                return state.ToString();
            });
            if (options.SaveEditedAcd) await Step("Save edited L5X through native ACD reopen", async () => {
                await SaveEditedAcd(); return true;
            });
        }
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
        if (serverFaulted)
            steps.Add(new { method = "SDK Offline cleanup", status = "skipped", reason = "native_server_faulted" });
        else try
        {
            // A failed Upload can leave Connected rather than Online.
            if (await project.ReadConnectedStateAsync() != LogixProject.ConnectedState.Offline)
                await Step("GoOfflineAsync:cleanup", async () => { await project.GoOfflineAsync(); return true; });
            await Step("ReadConnectedStateAsync:cleanup", async () => {
                var state = await project.ReadConnectedStateAsync();
                if (state != LogixProject.ConnectedState.Offline) throw new InvalidOperationException("SDK cleanup did not report Offline");
                return state.ToString();
            });
            sdkOfflineConfirmed = true;
        }
        catch (Exception error) { passed = false; ObserveServerFault(error); }
        try { project.Dispose(); }
        catch (Exception error) { passed = false; ObserveServerFault(error); steps.Add(new { method = "Dispose", status = "failed", error = error.Message }); }
    }
}
string? workingHash = null;
try { workingHash = Hash(); }
catch (IOException) { }
catch (UnauthorizedAccessException) { }
var unchanged = workingHash == options.SourceSha256;
// Upload merges into the private working file. Its original baseline and the
// emulator's bound source are preserved and independently rechecked by Python.
passed &= workingHash is not null && (unchanged || options.Operation == "upload" && !options.UploadNewProject);
object? newProjectUpload = null;
if (options.UploadNewProject)
{
    string? createdHash = null;
    try {
        if (File.Exists(newUploadPath) && new FileInfo(newUploadPath).Length is >= 8 and <= 100_000_000)
            createdHash = Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(newUploadPath))).ToLowerInvariant();
    }
    catch (IOException) { }
    catch (UnauthorizedAccessException) { }
    newProjectUpload = new { factoryCompleted = newUploadCompleted, fileCreated = createdHash is not null,
        acdSha256 = createdHash, nativeAcdReopened = false, nativeValidity = "NOT ASSESSED" };
    passed &= newUploadCompleted && createdHash is not null && sdkOfflineConfirmed;
}
await File.WriteAllTextAsync(args[1], JsonSerializer.Serialize(new {
    status = passed ? "succeeded" : "failed", operation = options.Operation,
    sourceUnchanged = unchanged, workingProjectUnchanged = unchanged, workingProjectSha256 = workingHash,
    controllerSourceSha256 = controllerSourceHash, steps, events = logger.Events.ToArray(),
    backendReadRecoveries, serverFaulted, sdkOfflineConfirmed, savedEditedProject, savedUploadedProject, savedDownloadedProject, uploadedContent, savedUploadedSnapshot,
    uploadNewProject = options.UploadNewProject, newProjectUpload,
    eventsTruncated = logger.Truncated, nativeControllerEquivalence = "NOT ASSESSED"
}, new JsonSerializerOptions { WriteIndented = true }));
return passed ? 0 : 1;

sealed record Options(string Project, string SourceSha256, string CommunicationsPath, string Operation, string[] Tags,
                      string? BackendUrl = null, string? InstanceId = null, EditOptions? Edit = null,
                      string TagReadType = "BYTE_ARRAY", bool ApplySupportedEdits = false,
                      EditOptions? SecondEdit = null, bool ReconnectEdits = false,
                      bool SaveEditedAcd = false, string[]? PostEditTags = null, string? ControllerSourceSha256 = null,
                      bool SaveUploadedAcd = false, bool UploadNewProject = false, bool SaveDownloadedAcd = false,
                      UploadContentOptions? UploadContent = null, bool SnapshotUploadedAcd = false, string? SnapshotBaseline = null,
                      bool ExportDownloadedL5x = false, bool ExportUploadedTags = false)
{
    public string[] EditTags => PostEditTags ?? Array.Empty<string>();
}
sealed record UploadContentOptions([property: JsonPropertyName("sourceL5xSha256")] string SourceL5xSha256,
    [property: JsonPropertyName("tags")] UploadTag[] Tags, [property: JsonPropertyName("routines")] UploadRoutine[] Routines,
    [property: JsonPropertyName("programs")] UploadProgram[] Programs);
sealed record UploadProgram([property: JsonPropertyName("name")] string Name, [property: JsonPropertyName("xpath")] string XPath,
    [property: JsonPropertyName("fileName")] string FileName);
sealed record UploadTag([property: JsonPropertyName("name")] string Name, [property: JsonPropertyName("xpath")] string XPath,
    [property: JsonPropertyName("expectedHex")] string ExpectedHex, [property: JsonPropertyName("constant")] bool Constant = false,
    [property: JsonPropertyName("typeCode")] int TypeCode = 0, [property: JsonPropertyName("dimensions")] int[]? Dimensions = null);
sealed record UploadRoutine([property: JsonPropertyName("program")] string Program, [property: JsonPropertyName("name")] string Name,
    [property: JsonPropertyName("xpath")] string XPath, [property: JsonPropertyName("fileName")] string FileName,
    [property: JsonPropertyName("expectedRungs")] string[] ExpectedRungs);
sealed record EditOptions(string File, string Sha256, string XPath, uint InsertPosition, uint ReplaceCount, string ImportOption,
                          long? BaseRevision = null, JsonElement? BeforeRungs = null, JsonElement? ExpectedRungs = null);
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
