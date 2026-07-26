using System.Text;
using WolvenKit.RED4.Archive.CR2W;
using WolvenKit.RED4.Archive.IO;
using WolvenKit.RED4.Types;
using static WolvenKit.RED4.Types.Enums;

namespace NpvPhotoMode;

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
            Console.Error.WriteLine($"npv-photomode: {ex.Message}");
            return 1;
        }
    }

    private static int Run(string[] args)
    {
        if (args.Length == 0)
            throw new ArgumentException(Usage);

        return args[0] switch
        {
            "build-icon" => BuildIcon(args[1..]),
            "build-localization" => BuildLocalization(args[1..]),
            "author-metadata" => AuthorMetadata(args[1..]),
            "inspect" => Inspect(args[1..]),
            _ => throw new ArgumentException($"Unknown command '{args[0]}'.\n{Usage}"),
        };
    }

    private static int BuildIcon(string[] args)
    {
        var values = ParseOptions(args, "--dds", "--xbm", "--inkatlas", "--xbm-depot");
        var ddsPath = values["--dds"];
        var xbmPath = values["--xbm"];
        var atlasPath = values["--inkatlas"];
        var xbmDepot = values["--xbm-depot"];
        var partName = values.GetValueOrDefault("--part", "custom_icon");

        var payload = ReadDxt5Payload(ddsPath, 200, 200);
        var blobSize = checked((uint)payload.Length);
        var header = new rendRenderTextureBlobHeader
        {
            Version = 2,
            Flags = 1,
            SizeInfo = new rendRenderTextureBlobSizeInfo
            {
                Width = 200,
                Height = 200,
                Depth = 1,
            },
            TextureInfo = new rendRenderTextureBlobTextureInfo
            {
                Type = GpuWrapApieTextureType.TEXTYPE_2D,
                TextureDataSize = blobSize,
                SliceSize = blobSize,
                DataAlignment = 8,
                SliceCount = 1,
                MipCount = 1,
            },
        };
        header.MipMapInfo.Add(new rendRenderTextureBlobMipMapInfo
        {
            Layout = new rendRenderTextureBlobMemoryLayout
            {
                RowPitch = 800,
                SlicePitch = blobSize,
            },
            Placement = new rendRenderTextureBlobPlacement
            {
                Offset = 0,
                Size = blobSize,
            },
        });
        var blob = new rendRenderTextureBlobPC
        {
            Header = header,
            TextureData = new SerializationDeferredDataBuffer(payload),
        };
        var bitmap = new CBitmapTexture
        {
            Width = 200,
            Height = 200,
            Depth = 1,
            Setup = new STextureGroupSetup
            {
                Group = GpuWrapApieTextureGroup.TEXG_Generic_UI,
                Compression = ETextureCompression.TCM_DXTAlpha,
                RawFormat = ETextureRawFormat.TRF_TrueColor,
                IsStreamable = false,
                HasMipchain = false,
                IsGamma = true,
                AllowTextureDowngrade = false,
            },
        };
        bitmap.RenderTextureResource.RenderResourceBlobPC =
            new CHandle<IRenderResourceBlob>(blob);
        WriteCr2W(new CR2WFile { RootChunk = bitmap }, xbmPath);

        var mapper = new inkTextureAtlasMapper
        {
            PartName = partName,
            ClippingRectInPixels = new Rect
            {
                Left = 0,
                Top = 0,
                Right = 200,
                Bottom = 200,
            },
            ClippingRectInUVCoords = new RectF
            {
                Left = 0,
                Top = 0,
                Right = 1,
                Bottom = 1,
            },
        };
        var atlas = new inkTextureAtlas
        {
            ActiveTexture = inkTextureType.StaticTexture,
            IsSingleTextureMode = true,
            TextureResolution = inkETextureResolution.UltraHD_3840_2160,
        };
        atlas.Slots[0].Texture = new CResourceAsyncReference<CBitmapTexture>(
            xbmDepot, InternalEnums.EImportFlags.Soft);
        atlas.Slots[0].Parts.Add(mapper);
        WriteCr2W(new CR2WFile { RootChunk = atlas }, atlasPath);

        ValidateIcon(xbmPath, atlasPath, xbmDepot, partName);
        Console.WriteLine($"Wrote Photo Mode icon: {xbmPath}");
        Console.WriteLine($"Wrote Photo Mode atlas: {atlasPath}");
        return 0;
    }

    private static int BuildLocalization(string[] args)
    {
        var values = ParseOptions(args, "--output", "--key", "--value");
        var output = values["--output"];
        var key = values["--key"];
        var value = values["--value"];

        var entries = new localizationPersistenceOnScreenEntries();
        entries.Entries.Add(new localizationPersistenceOnScreenEntry
        {
            SecondaryKey = key,
            FemaleVariant = value,
            MaleVariant = value,
        });
        var resource = new JsonResource
        {
            Root = new CHandle<ISerializable>(entries),
        };
        WriteCr2W(new CR2WFile { RootChunk = resource }, output);
        ValidateLocalization(output, key, value);
        Console.WriteLine($"Wrote Photo Mode localization: {output}");
        return 0;
    }

    private static int AuthorMetadata(string[] args)
    {
        var values = ParseOptions(
            args,
            "--dds",
            "--xbm",
            "--inkatlas",
            "--xbm-depot",
            "--localization",
            "--key",
            "--value");
        var partName = values.GetValueOrDefault("--part", "custom_icon");
        BuildIcon([
            "--dds", values["--dds"],
            "--xbm", values["--xbm"],
            "--inkatlas", values["--inkatlas"],
            "--xbm-depot", values["--xbm-depot"],
            "--part", partName,
        ]);
        BuildLocalization([
            "--output", values["--localization"],
            "--key", values["--key"],
            "--value", values["--value"],
        ]);
        return 0;
    }

    private static int Inspect(string[] args)
    {
        var values = ParseOptions(args, "--file");
        var file = ReadCr2W(values["--file"]);
        Console.WriteLine(file.RootChunk?.GetType().Name ?? "null");
        return 0;
    }

    private static Dictionary<string, string> ParseOptions(string[] args, params string[] required)
    {
        var values = new Dictionary<string, string>();
        for (var i = 0; i < args.Length; i++)
        {
            if (!args[i].StartsWith("--", StringComparison.Ordinal))
                throw new ArgumentException($"Unexpected argument: {args[i]}");
            if (i + 1 >= args.Length)
                throw new ArgumentException($"Missing value for {args[i]}");
            values[args[i]] = args[++i];
        }
        foreach (var option in required)
        {
            if (!values.TryGetValue(option, out var value) || string.IsNullOrWhiteSpace(value))
                throw new ArgumentException($"Missing required option {option}.");
        }
        return values;
    }

    private static void ValidateIcon(
        string xbmPath, string atlasPath, string expectedDepot, string expectedPart)
    {
        var xbm = ReadCr2W(xbmPath).RootChunk as CBitmapTexture
            ?? throw new InvalidDataException("Generated XBM has the wrong root type.");
        if (xbm.Setup.Group != GpuWrapApieTextureGroup.TEXG_Generic_UI)
            throw new InvalidDataException($"Generated XBM group is {xbm.Setup.Group}, expected TEXG_Generic_UI.");
        if (xbm.Setup.Compression != ETextureCompression.TCM_DXTAlpha)
            throw new InvalidDataException($"Generated XBM compression is {xbm.Setup.Compression}, expected TCM_DXTAlpha.");
        if (xbm.Setup.IsStreamable || xbm.Setup.HasMipchain || !xbm.Setup.IsGamma)
            throw new InvalidDataException("Generated XBM has invalid UI texture flags.");

        var atlas = ReadCr2W(atlasPath).RootChunk as inkTextureAtlas
            ?? throw new InvalidDataException("Generated atlas has the wrong root type.");
        var slot = atlas.Slots[0];
        var depot = slot.Texture.DepotPath.GetResolvedText() ?? "";
        if (!string.Equals(depot, expectedDepot, StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException($"Atlas points at '{depot}', expected '{expectedDepot}'.");
        if (slot.Parts.Count != 1 || slot.Parts[0].PartName.GetResolvedText() != expectedPart)
            throw new InvalidDataException($"Atlas does not expose the '{expectedPart}' part.");
    }

    private static void ValidateLocalization(string path, string expectedKey, string expectedValue)
    {
        var file = ReadCr2W(path);
        if (file.RootChunk is not JsonResource { Root.Chunk: localizationPersistenceOnScreenEntries entries })
            throw new InvalidDataException("Generated localization has the wrong root type.");
        if (entries.Entries.Count != 1 ||
            entries.Entries[0].SecondaryKey != expectedKey ||
            entries.Entries[0].FemaleVariant != expectedValue)
        {
            throw new InvalidDataException("Generated localization entry did not round-trip.");
        }
    }

    private static CR2WFile ReadCr2W(string path)
    {
        using var fs = File.OpenRead(path);
        using var reader = new CR2WReader(new MemoryStream(ReadAllBytes(fs)));
        reader.ReadFile(out var file, true);
        return file ?? throw new InvalidDataException($"Could not read CR2W file: {path}");
    }

    private static void WriteCr2W(CR2WFile file, string path)
    {
        var parent = Path.GetDirectoryName(path);
        if (!string.IsNullOrEmpty(parent))
            Directory.CreateDirectory(parent);
        using var ms = new MemoryStream();
        using (var writer = new CR2WWriter(ms, Encoding.UTF8, true))
            writer.WriteFile(file);
        File.WriteAllBytes(path, ms.ToArray());
    }

    private static byte[] ReadAllBytes(Stream stream)
    {
        using var ms = new MemoryStream();
        stream.CopyTo(ms);
        return ms.ToArray();
    }

    private static byte[] ReadDxt5Payload(string path, int expectedWidth, int expectedHeight)
    {
        var bytes = File.ReadAllBytes(path);
        if (bytes.Length < 128 ||
            bytes[0] != (byte)'D' || bytes[1] != (byte)'D' ||
            bytes[2] != (byte)'S' || bytes[3] != (byte)' ')
        {
            throw new InvalidDataException($"{path} is not a legacy DDS file.");
        }
        var headerSize = BitConverter.ToUInt32(bytes, 4);
        var height = BitConverter.ToUInt32(bytes, 12);
        var width = BitConverter.ToUInt32(bytes, 16);
        var fourCc = Encoding.ASCII.GetString(bytes, 84, 4);
        if (headerSize != 124 || width != expectedWidth || height != expectedHeight)
        {
            throw new InvalidDataException(
                $"DDS must be {expectedWidth}x{expectedHeight}; got {width}x{height}.");
        }
        if (fourCc != "DXT5")
            throw new InvalidDataException($"DDS must use DXT5 compression; got '{fourCc}'.");

        var payload = bytes[128..];
        var expectedBytes = checked(expectedWidth * expectedHeight);
        if (payload.Length != expectedBytes)
        {
            throw new InvalidDataException(
                $"DDS must contain one DXT5 mip ({expectedBytes} bytes); got {payload.Length}.");
        }
        return payload;
    }

    private const string Usage =
        "Usage:\n" +
        "  npv-photomode build-icon --dds <200x200 DXT5 icon.dds> --xbm <icon.xbm> " +
        "--inkatlas <icon.inkatlas> --xbm-depot <depot path> [--part custom_icon]\n" +
        "  npv-photomode build-localization --output <file.json> --key <key> --value <name>\n" +
        "  npv-photomode author-metadata --dds <icon.dds> --xbm <icon.xbm> " +
        "--inkatlas <icon.inkatlas> --xbm-depot <depot path> --localization <file.json> " +
        "--key <key> --value <name> [--part custom_icon]\n" +
        "  npv-photomode inspect --file <cr2w-file>";
}
