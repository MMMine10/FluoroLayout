# FluoroLayout

![FluoroLayout icon](FluoroLayout.png)

FluoroLayout is a local Windows application for arranging multichannel immunofluorescence TIFF images into publication-ready scientific figures. It supports flexible fluorescence and brightfield channel combinations, per-group missing channels, selected-channel merges, calibrated scale bars, regions of interest, magnified panels, customizable layouts, and TIFF, PNG, or SVG export.

All images are processed locally. FluoroLayout does not upload experimental data to an external server.

## Key features

- Import 8-bit, 16-bit, and 32-bit TIFF images, including multipage stacks.
- Use blue, green, red, and brightfield channels in flexible combinations.
- Keep experimental groups aligned even when a group has a missing channel.
- Create Merge images only from the fluorescence channels selected for that group.
- Customize channel order, channel names, label colors, spacing, and font size.
- Arrange figures horizontally or vertically.
- Add rectangular or fixed-size square regions of interest.
- Place magnified regions in separate panels or as corner insets.
- Show Merge-only or multichannel magnified views.
- Calibrate scale bars using micrometers per pixel or full-field width.
- Export TIFF, PNG, and SVG figures with an opaque or transparent background.

## Download for Windows

Download the latest Windows package from the repository's **Releases** page. Extract the ZIP archive and double-click `FluoroLayout.exe`. The standalone release does not require Python.

The current executable is not signed with a commercial code-signing certificate, so Windows SmartScreen may show an **Unknown publisher** warning. Download the application only from this repository and compare its SHA-256 checksum with the checksum published on the Release page.

## Run from source

Requirements:

- Windows 10 or later
- Python 3.10 or later

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python web_app.py
```

The application opens a local browser interface. An internet connection is not required after dependencies have been installed.

## Build the Windows executable

```powershell
powershell -ExecutionPolicy Bypass -File .\build_release.ps1
```

The resulting executable is created under `dist\`. Build artifacts are intentionally excluded from source control.

## Scale-bar calibration

TIFF metadata such as `72 pixels/inch` describes print or display resolution and does not provide the physical microscopy calibration. Use either a verified `µm/px` value or the physical width of the complete field of view. The default `0.325 µm/px` is only a starting value and must be checked against the microscope acquisition metadata for each dataset.

## Scientific-use notice

Users are responsible for verifying image integrity, channel assignments, scale-bar calibration, and final figure accuracy. Brightness, contrast, percentile normalization, and gamma settings should be applied consistently to comparable groups and reported according to the target journal's image-processing policy. FluoroLayout assists figure preparation but does not replace retention, validation, or quantitative analysis of the original microscopy data.

## Privacy

Imported files are copied only to a temporary directory on the local computer and are removed when the application closes normally. Do not commit patient data, unpublished microscopy images, identifying metadata, or other confidential research material to this repository.

## License

Copyright © 2026 FluoroLayout contributors. All rights reserved. See [LICENSE](LICENSE).

## Third-party software

FluoroLayout uses open-source Python packages. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for attribution and upstream license links.
