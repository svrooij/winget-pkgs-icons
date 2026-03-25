# winget-pkgs-icons

A community-maintained repository of high-resolution icons (1024×1024 PNG) for all packages in the [Windows Package Manager (winget)](https://github.com/microsoft/winget-pkgs).

## Goal

The goal of this repository is to collect high-resolution icons for all packages available in winget. These icons can be used by tools, applications, or websites that want to display package icons alongside their winget package listings.

## Image URLs

Images are hosted on **GitHub Pages** and can be accessed at:

```
https://svrooij.github.io/winget-pkgs-icons/{path}
```

### Naming Convention

Each winget package has a **Package ID** in the format `Publisher.AppName` or `Publisher.AppName.Locale`.

The image path is derived from the Package ID as follows:

1. Split the Package ID by `.`
2. The first segment is the **publisher** (e.g., `Microsoft`)
3. The remaining segments form the **app path** (e.g., `Teams`, `Firefox/az`)
4. The top-level directory is the **first letter** of the publisher (lowercase)
5. All path components are **lowercase**

**Examples:**

| Package ID | Image Path | Image URL |
|---|---|---|
| `Microsoft.Teams` | `m/microsoft/teams.png` | `https://winget.svrooij.io/m/microsoft/teams.png` |
| `Mozilla.Firefox` | `m/mozilla/firefox.png` | `https://winget.svrooij.io/m/mozilla/firefox.png` |
| `Mozilla.Firefox.az` | `m/mozilla/firefox/az.png` | `https://winget.svrooij.io/m/mozilla/firefox/az.png` |
| `Google.Chrome` | `g/google/chrome.png` | `https://winget.svrooij.io/g/google/chrome.png` |

## Contributing

### Adding an Icon

1. Fork this repository
2. Find the **Package ID** in [winget-pkgs](https://github.com/microsoft/winget-pkgs)
3. Convert the Package ID to an image path using the [naming convention](#naming-convention) above
4. Add a **1024×1024 PNG** image at the correct path
5. Submit a Pull Request

### Image Requirements

- **Format**: PNG
- **Size**: Exactly 1024×1024 pixels
- **Path**: Must follow the naming convention described above

Pull Requests are automatically validated to ensure all images meet these requirements. A failing validation check means the image does not meet the requirements and the PR will not be merged.

## License

Images in this repository are contributed by the community. Please ensure you have the rights to submit the icon you are contributing. Icons are typically owned by the respective software vendor.

See [LICENSE](LICENSE) for the repository license.
