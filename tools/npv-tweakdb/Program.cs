using System.Text.Json;
using WolvenKit.RED4.TweakDB;
using WolvenKit.RED4.Types;

namespace NpvTweakDb;

public sealed record ItemRecord(
    string ItemId,
    string RecordType,
    string AppearanceName,
    string AppearanceResourceName,
    string EntityName,
    IReadOnlyList<string> AppearanceSuffixes,
    bool Resolved);

public static class Program
{
    public static int Main(string[] args)
    {
        try
        {
            var (tweakDbPaths, itemIds) = ParseArgs(args);
            var databases = tweakDbPaths.Select(ReadDatabase).ToList();
            var records = itemIds.Select(id => ReadItem(databases, id)).ToList();
            Console.WriteLine(
                JsonSerializer.Serialize(
                    records,
                    new JsonSerializerOptions
                    {
                        WriteIndented = true,
                        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
                    }));
            return 0;
        }
        catch (Exception error)
        {
            Console.Error.WriteLine($"npv-tweakdb: {error}");
            return 1;
        }
    }

    private static (List<string> TweakDbs, List<string> ItemIds) ParseArgs(string[] args)
    {
        var tweakDbs = new List<string>();
        string? itemsJson = null;
        var directItems = new List<string>();
        for (var index = 0; index < args.Length; index++)
        {
            switch (args[index])
            {
                case "--tweakdb" when index + 1 < args.Length:
                    tweakDbs.Add(args[++index]);
                    break;
                case "--items-json" when index + 1 < args.Length:
                    itemsJson = args[++index];
                    break;
                default:
                    if (args[index].StartsWith("-", StringComparison.Ordinal))
                        throw new ArgumentException($"Unknown option: {args[index]}");
                    directItems.Add(args[index]);
                    break;
            }
        }
        if (tweakDbs.Count == 0)
            throw new ArgumentException("At least one --tweakdb path is required.");
        var itemIds = itemsJson is null
            ? directItems
            : JsonSerializer.Deserialize<List<string>>(File.ReadAllText(itemsJson)) ?? [];
        if (itemIds.Count == 0)
            throw new ArgumentException("At least one item ID is required.");
        return (tweakDbs, itemIds);
    }

    private static TweakDB ReadDatabase(string path)
    {
        using var stream = File.OpenRead(path);
        using var reader = new TweakDBReader(stream);
        var result = reader.ReadFile(out var database);
        if (result != EFileReadErrorCodes.NoError || database is null)
            throw new InvalidDataException($"Could not read TweakDB '{path}': {result}");
        return database;
    }

    private static ItemRecord ReadItem(IReadOnlyList<TweakDB> databases, string rawId)
    {
        var itemId = rawId.StartsWith("Items.", StringComparison.Ordinal)
            ? rawId
            : $"Items.{rawId}";
        var recordType = databases
            .Reverse()
            .Select(database => database.GetRecordType((TweakDBID)itemId))
            .FirstOrDefault(type => type is not null);
        if (recordType is null)
            return new ItemRecord(itemId, "", "", "", "", [], false);
        if (!typeof(gamedataItem_Record).IsAssignableFrom(recordType))
            return new ItemRecord(itemId, recordType.Name, "", "", "", [], false);

        return new ItemRecord(
            itemId,
            recordType.Name,
            GetCName(databases, $"{itemId}.appearanceName"),
            GetCName(databases, $"{itemId}.appearanceResourceName"),
            GetCName(databases, $"{itemId}.entityName"),
            GetTweakDbIds(databases, $"{itemId}.appearanceSuffixes"),
            true);
    }

    private static string GetCName(IReadOnlyList<TweakDB> databases, string path)
    {
        foreach (var database in databases.Reverse())
        {
            if (database.Flats.GetValue(path) is CName value)
                return value.GetResolvedText() ?? $"0x{value.GetRedHash():X16}";
        }
        return "";
    }

    private static IReadOnlyList<string> GetTweakDbIds(
        IReadOnlyList<TweakDB> databases,
        string path)
    {
        foreach (var database in databases.Reverse())
        {
            if (database.Flats.GetValue(path) is CArray<TweakDBID> values)
                return values.Select(FormatTweakDbId).ToList();
        }
        return [];
    }

    private static string FormatTweakDbId(TweakDBID value)
    {
        return value.GetResolvedText() ?? $"0x{(ulong)value:X16}";
    }
}
