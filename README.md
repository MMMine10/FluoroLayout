# FluoroLayout

FluoroLayout is a local, user-friendly Windows application for creating publication-ready figures from multichannel immunofluorescence TIFF images.

The software supports flexible combinations of blue, green, red, and brightfield channels. Experimental groups may contain different channel sets while remaining aligned to a consistent figure layout. Merge images are generated only from the fluorescence channels selected for each group.

FluoroLayout provides customizable channel order and labels, horizontal or vertical layouts, transparent backgrounds, region-of-interest boxes, corner insets, separate magnified panels, and calibrated scale bars. Scale-bar calibration can be entered either as micrometers per pixel or as the physical width of the full image field. Figures can be exported in TIFF, PNG, or SVG format.

All image processing is performed locally on the user's computer. No experimental images are uploaded to an external server.

## Key Features

- Import 8-bit, 16-bit, and 32-bit TIFF images
- Support blue, green, red, and brightfield channels
- Create merges from selected fluorescence channels only
- Allow missing channels in individual experimental groups
- Customize channel order, channel names, and label colors
- Arrange figures horizontally or vertically
- Add rectangular or fixed-size square regions of interest
- Display magnified regions as corner insets or separate panels
- Show Merge-only or multichannel magnified views
- Add calibrated scale bars using µm/px or full-field width
- Export publication-ready TIFF, PNG, and SVG files
- Use white or transparent figure backgrounds
- Process all images locally for data privacy

## Windows Release

Download the latest Windows version from the GitHub Releases page. The standalone executable does not require Python to be installed.

Because the current release is not digitally signed with a commercial code-signing certificate, Windows SmartScreen may display an “Unknown publisher” warning. Users should download the software only from the official repository and verify the provided SHA-256 checksum.

## Scientific Use Notice

Users are responsible for verifying image integrity, channel assignments, scale-bar calibration, and final figure accuracy. Brightness, contrast, normalization, and gamma adjustments should be applied consistently and reported according to the image-processing policies of the target journal.

FluoroLayout is intended to assist scientific figure preparation and does not replace retention or analysis of the original microscopy data.
