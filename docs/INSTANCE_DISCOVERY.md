# Instance discovery

`ATM10-Agent` resolves local Minecraft and ATM10 paths with an env-first posture.

This is intentionally separate from the host-profile support claim. Fedora local
development can use the discovery artifact without claiming full Linux ATM10
product-edge parity.

## Explicit inputs

Use explicit environment variables when possible:

```bash
export MINECRAFT_DIR="$HOME/.minecraft"
export ATM10_DIR="$HOME/.local/share/PrismLauncher/instances/All the Mods 10"
python scripts/discover_instance.py --runs-dir runs/fedora-discovery
```

`ATM10_DIR` is the strongest signal and wins over launcher scans.

## Fedora/Linux fallback scan

When `ATM10_DIR` is not set, Linux scans common local launcher roots after the
base Minecraft roots:

- `$MINECRAFT_DIR/versions`
- `$MINECRAFT_DIR/instances`
- `$XDG_DATA_HOME/PrismLauncher/instances`
- `$XDG_DATA_HOME/PolyMC/instances`
- `$XDG_DATA_HOME/com.modrinth.theseus/profiles`
- Flatpak PrismLauncher and Modrinth data roots under `~/.var/app`
- selected home CurseForge instance roots

The scanner only looks for directory names containing `atm10` or
`all the mods 10`; it does not recursively crawl the filesystem.

## Windows preservation

Windows keeps the existing fallback order:

1. `MINECRAFT_DIR`
2. `%APPDATA%/.minecraft`
3. `~/AppData/Roaming/.minecraft`

This keeps the Windows ATM10 product edge stable while Fedora gains a real
local-development discovery path.
