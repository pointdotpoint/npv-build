using System.Text;
using WolvenKit.RED4.Archive.CR2W;
using WolvenKit.RED4.Archive.IO;
using WolvenKit.RED4.Types;

namespace NpvInject;

public static class Program
{
    public static int Main(string[] args)
    {
        try
        {
            return Run(args);
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine($"npv-inject: {ex.Message}");
            return 1;
        }
    }

    private static int Run(string[] args)
    {
        var (appPath, jsonPath, donorPath, faceRig, facialSetup, faceGraph, skipDonorHairDangle, appearanceIndex, verbose) = ParseArgs(args);

        if (!File.Exists(appPath))
        {
            Console.Error.WriteLine($"File not found: {appPath}");
            return 1;
        }
        if (!File.Exists(jsonPath))
        {
            Console.Error.WriteLine($"File not found: {jsonPath}");
            return 1;
        }

        string? appearanceName;
        List<ComponentSpec> specs;
        try
        {
            (appearanceName, specs) = ComponentInjector.ParseSpecFile(jsonPath);
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine($"Failed to parse component spec: {ex.Message}");
            return 1;
        }

        if (specs.Count == 0)
        {
            Console.Error.WriteLine("No components in spec file.");
            return 1;
        }

        CR2WFile cr2w;
        try
        {
            using var fs = File.OpenRead(appPath);
            using var reader = new CR2WReader(new MemoryStream(ReadAllBytes(fs)));
            reader.ReadFile(out var file, true);
            if (file is null)
            {
                Console.Error.WriteLine("Failed to read .app file: CR2WReader returned null.");
                return 2;
            }
            cr2w = file;
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine($"Failed to parse .app file: {ex.Message}");
            return 2;
        }

        if (cr2w.RootChunk is not appearanceAppearanceResource resource)
        {
            Console.Error.WriteLine(
                $".app RootChunk is {cr2w.RootChunk?.GetType().Name ?? "null"}, " +
                "expected appearanceAppearanceResource.");
            return 2;
        }

        if (appearanceIndex >= resource.Appearances.Count)
        {
            Console.Error.WriteLine(
                $"Appearance index {appearanceIndex} out of range " +
                $"(file has {resource.Appearances.Count} appearance(s)).");
            return 2;
        }

        var handle = resource.Appearances[appearanceIndex];
        if (handle.Chunk is not appearanceAppearanceDefinition appearance)
        {
            Console.Error.WriteLine(
                $"Appearance at index {appearanceIndex} is not an " +
                "appearanceAppearanceDefinition.");
            return 2;
        }

        try
        {
            if (appearanceName is not null)
            {
                appearance.Name = appearanceName;
                if (verbose)
                    Console.WriteLine($"Appearance name set to: {appearanceName}");
            }

            // Keep only the target appearance, remove extras
            while (resource.Appearances.Count > appearanceIndex + 1)
                resource.Appearances.RemoveAt(resource.Appearances.Count - 1);
            while (resource.Appearances.Count > 1 && appearanceIndex > 0)
            {
                resource.Appearances.RemoveAt(0);
                appearanceIndex--;
            }

            // Copy infrastructure from donor .app if provided
            if (donorPath is not null)
            {
                if (verbose)
                    Console.WriteLine($"Copying infrastructure from {Path.GetFileName(donorPath)}...");

                var donorAppearance = ReadDonorAppearance(donorPath);
                if (donorAppearance is not null)
                    ComponentInjector.CopyInfrastructure(donorAppearance, appearance, faceRig, facialSetup, faceGraph, skipDonorHairDangle, verbose);
                else
                    Console.Error.WriteLine("Warning: could not read donor appearance");
            }

            if (verbose)
                Console.WriteLine($"Injecting {specs.Count} component(s) into {Path.GetFileName(appPath)}...");

            ComponentInjector.Inject(appearance, specs, verbose);
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine($"Component injection failed: {ex.Message}");
            return 3;
        }

        try
        {
            using var ms = new MemoryStream();
            using (var writer = new CR2WWriter(ms, Encoding.UTF8, true))
            {
                writer.WriteFile(cr2w);
            }
            File.WriteAllBytes(appPath, ms.ToArray());
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine($"Failed to write .app file: {ex.Message}");
            return 4;
        }

        if (verbose)
            Console.WriteLine($"Done. {specs.Count} mesh + infrastructure component(s) injected.");

        return 0;
    }

    private static appearanceAppearanceDefinition? ReadDonorAppearance(string donorPath)
    {
        using var fs = File.OpenRead(donorPath);
        using var reader = new CR2WReader(new MemoryStream(ReadAllBytes(fs)));
        reader.ReadFile(out var donorFile, true);
        if (donorFile?.RootChunk is not appearanceAppearanceResource donorResource)
            return null;
        if (donorResource.Appearances.Count == 0)
            return null;
        return donorResource.Appearances[0].Chunk as appearanceAppearanceDefinition;
    }

    private static byte[] ReadAllBytes(Stream stream)
    {
        using var ms = new MemoryStream();
        stream.CopyTo(ms);
        return ms.ToArray();
    }

    private static (string appPath, string jsonPath, string? donorPath, string? faceRig, string? facialSetup, string? faceGraph, bool skipDonorHairDangle, int appearanceIndex, bool verbose) ParseArgs(string[] args)
    {
        string? appPath = null;
        string? jsonPath = null;
        string? donorPath = null;
        string? faceRig = null;
        string? facialSetup = null;
        string? faceGraph = null;
        bool skipDonorHairDangle = false;
        int appearanceIndex = 0;
        bool verbose = false;

        for (int i = 0; i < args.Length; i++)
        {
            switch (args[i])
            {
                case "--appearance-index" when i + 1 < args.Length:
                    if (!int.TryParse(args[++i], out appearanceIndex) || appearanceIndex < 0)
                        throw new ArgumentException($"Invalid appearance index: {args[i]}");
                    break;
                case "--donor" when i + 1 < args.Length:
                    donorPath = args[++i];
                    break;
                case "--face-rig" when i + 1 < args.Length:
                    faceRig = args[++i];
                    break;
                case "--facial-setup" when i + 1 < args.Length:
                    facialSetup = args[++i];
                    break;
                case "--face-graph" when i + 1 < args.Length:
                    faceGraph = args[++i];
                    break;
                case "--skip-donor-hair-dangle":
                    skipDonorHairDangle = true;
                    break;
                case "--verbose":
                    verbose = true;
                    break;
                default:
                    if (args[i].StartsWith('-'))
                        throw new ArgumentException($"Unknown option: {args[i]}");
                    if (appPath is null)
                        appPath = args[i];
                    else if (jsonPath is null)
                        jsonPath = args[i];
                    else
                        throw new ArgumentException($"Unexpected argument: {args[i]}");
                    break;
            }
        }

        if (appPath is null || jsonPath is null)
            throw new ArgumentException(
                "Usage: npv-inject <app-file> <components-json> [--donor <donor.app>] [--face-rig <path>] [--facial-setup <path>] [--verbose]");

        return (appPath, jsonPath, donorPath, faceRig, facialSetup, faceGraph, skipDonorHairDangle, appearanceIndex, verbose);
    }
}
