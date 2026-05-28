using System.Text.Json;
using WolvenKit.RED4.Types;

namespace NpvInject;

public record ComponentSpec(
    string Type,
    string Name,
    string Mesh,
    string MeshAppearance,
    string BindTo,
    string? Graph = null,
    string? Rig = null);

public static class ComponentInjector
{
    private static readonly HashSet<string> s_meshTypes = new()
    {
        "entSkinnedMeshComponent",
        "entGarmentSkinnedMeshComponent",
    };

    private static readonly HashSet<string> s_validTypes = new()
    {
        "entSkinnedMeshComponent",
        "entGarmentSkinnedMeshComponent",
        "entAnimatedComponent",
        "entMorphTargetSkinnedMeshComponent",
    };

    private static readonly HashSet<string> s_infrastructureTypes = new()
    {
        "entAnimatedComponent",
        "entAnimationSetupExtensionComponent",
        "entLightBlockingComponent",
        "entSlotComponent",
        "entVisualControllerComponent",
    };

    public static (string? AppearanceName, List<ComponentSpec> Specs) ParseSpecFile(string jsonPath)
    {
        var text = File.ReadAllText(jsonPath);
        using var doc = JsonDocument.Parse(text);
        var root = doc.RootElement;

        string? appearanceName = root.TryGetProperty("appearance_name", out var anProp)
            ? anProp.GetString() : null;

        if (!root.TryGetProperty("components", out var componentsArr))
            throw new InvalidDataException("JSON missing 'components' array.");

        var specs = new List<ComponentSpec>();
        foreach (var elem in componentsArr.EnumerateArray())
        {
            var type = elem.GetProperty("type").GetString()
                ?? throw new InvalidDataException("Component missing 'type'.");
            var name = elem.GetProperty("name").GetString()
                ?? throw new InvalidDataException("Component missing 'name'.");
            var meshAppearance = elem.TryGetProperty("meshAppearance", out var maProp)
                ? maProp.GetString() ?? "default" : "default";
            var bindTo = elem.TryGetProperty("bindTo", out var btProp)
                ? btProp.GetString() ?? "root" : "root";

            var mesh = elem.TryGetProperty("mesh", out var meshProp)
                ? meshProp.GetString() ?? "" : "";
            var graph = elem.TryGetProperty("graph", out var graphProp)
                ? graphProp.GetString() : null;
            var rig = elem.TryGetProperty("rig", out var rigProp)
                ? rigProp.GetString() : null;

            if (!s_validTypes.Contains(type))
                throw new InvalidDataException($"Unknown component type: '{type}'.");

            specs.Add(new ComponentSpec(type, name, mesh, meshAppearance, bindTo, graph, rig));
        }

        return (appearanceName, specs);
    }

    public static void CopyInfrastructure(
        appearanceAppearanceDefinition source,
        appearanceAppearanceDefinition target,
        string? faceRigPath,
        string? facialSetupPath,
        string? faceGraphPath,
        bool skipDonorHairDangle,
        bool verbose)
    {
        target.Components ??= new CArray<entIComponent>();

        foreach (var comp in source.Components)
        {
            if (comp is entIComponent c &&
                s_infrastructureTypes.Contains(c.GetType().Name))
            {
                var compName = c.Name.GetResolvedText() ?? "";

                if (skipDonorHairDangle && compName == "hair_dangle")
                {
                    if (verbose)
                        Console.WriteLine($"  x [entAnimatedComponent] hair_dangle (skipped, using custom)");
                    continue;
                }

                if (c is entAnimatedComponent animated &&
                    compName == "face_rig")
                {
                    if (faceRigPath is not null)
                    {
                        animated.Rig = new CResourceReference<animRig>(
                            (ResourcePath)faceRigPath);
                    }
                    if (facialSetupPath is not null)
                    {
                        animated.FacialSetup = new CResourceAsyncReference<animFacialSetup>(
                            (ResourcePath)facialSetupPath);
                    }
                    if (faceGraphPath is not null)
                    {
                        animated.Graph = new CResourceReference<animAnimGraph>(
                            (ResourcePath)faceGraphPath);
                    }
                    if (verbose)
                        Console.WriteLine($"  = [entAnimatedComponent] face_rig (graph -> paperdoll_sermo)");
                }
                else if (verbose)
                {
                    Console.WriteLine($"  = [{c.GetType().Name}] {c.Name.GetResolvedText()}");
                }

                target.Components.Add(comp);
            }
        }
    }

    public static void Inject(
        appearanceAppearanceDefinition appearance,
        List<ComponentSpec> specs,
        bool verbose)
    {
        appearance.Components ??= new CArray<entIComponent>();

        foreach (var spec in specs)
        {
            var component = CreateComponent(spec);
            appearance.Components.Add(component);

            if (verbose)
                Console.WriteLine($"  + [{spec.Type}] {spec.Name} mesh={spec.Mesh[Math.Max(0, spec.Mesh.Length - 40)..]}");
        }
    }

    private static entIComponent CreateComponent(ComponentSpec spec)
    {
        if (spec.Type == "entAnimatedComponent")
            return CreateAnimated(spec);

        entIPlacedComponent component = spec.Type switch
        {
            "entSkinnedMeshComponent" => CreateSkinnedMesh(spec),
            "entGarmentSkinnedMeshComponent" => CreateGarmentMesh(spec),
            "entMorphTargetSkinnedMeshComponent" => CreateMorphTargetSkinnedMesh(spec),
            _ => throw new InvalidDataException($"Unknown component type: '{spec.Type}'."),
        };

        component.Name = spec.Name;

        var parentTransform = new entHardTransformBinding();
        parentTransform.BindName = spec.BindTo;
        component.ParentTransform = new CHandle<entITransformBinding>(parentTransform);

        return component;
    }

    private static entAnimatedComponent CreateAnimated(ComponentSpec spec)
    {
        var c = new entAnimatedComponent();
        c.Name = spec.Name;

        if (!string.IsNullOrEmpty(spec.Graph))
            c.Graph = new CResourceReference<animAnimGraph>(
                (ResourcePath)spec.Graph,
                InternalEnums.EImportFlags.Obligatory);

        if (!string.IsNullOrEmpty(spec.Rig))
            c.Rig = new CResourceReference<animRig>((ResourcePath)spec.Rig);

        var controlBinding = new entAnimationControlBinding();
        controlBinding.BindName = spec.BindTo;
        controlBinding.Enabled = true;
        c.ControlBinding = new CHandle<entAnimationControlBinding>(controlBinding);

        var parentTransform = new entHardTransformBinding();
        parentTransform.BindName = "root";
        c.ParentTransform = new CHandle<entITransformBinding>(parentTransform);

        return c;
    }

    private static entSkinnedMeshComponent CreateSkinnedMesh(ComponentSpec spec)
    {
        var c = new entSkinnedMeshComponent();
        c.MeshAppearance = spec.MeshAppearance;
        c.ChunkMask = ulong.MaxValue;

        if (!string.IsNullOrEmpty(spec.Mesh))
            c.Mesh = new CResourceAsyncReference<CMesh>((ResourcePath)spec.Mesh);

        var skinning = new entSkinningBinding();
        skinning.BindName = spec.BindTo;
        c.Skinning = new CHandle<entSkinningBinding>(skinning);

        return c;
    }

    private static entGarmentSkinnedMeshComponent CreateGarmentMesh(ComponentSpec spec)
    {
        var c = new entGarmentSkinnedMeshComponent();
        c.MeshAppearance = spec.MeshAppearance;
        c.ChunkMask = ulong.MaxValue;

        if (!string.IsNullOrEmpty(spec.Mesh))
            c.Mesh = new CResourceAsyncReference<CMesh>((ResourcePath)spec.Mesh);

        var skinning = new entSkinningBinding();
        skinning.BindName = spec.BindTo;
        c.Skinning = new CHandle<entSkinningBinding>(skinning);

        return c;
    }

    private static entMorphTargetSkinnedMeshComponent CreateMorphTargetSkinnedMesh(ComponentSpec spec)
    {
        var c = new entMorphTargetSkinnedMeshComponent();
        c.MeshAppearance = spec.MeshAppearance;
        c.ChunkMask = ulong.MaxValue;

        if (!string.IsNullOrEmpty(spec.Graph))
            c.MorphResource = new CResourceAsyncReference<MorphTargetMesh>((ResourcePath)spec.Graph);

        var skinning = new entSkinningBinding();
        skinning.BindName = spec.BindTo;
        c.Skinning = new CHandle<entSkinningBinding>(skinning);

        return c;
    }
}
