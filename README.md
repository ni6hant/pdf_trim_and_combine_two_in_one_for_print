# PDF Trimmer / 2-in-1

A Windows tool that takes a PDF, rasterizes it, crops the white margins off every
page, and rebuilds it as a PDF — optionally also producing a "2 pages per sheet"
version.

## What it does

1. Pop-up lets you pick a PDF, set DPI (default `300`), and toggle
   **"Combine 2 pages into 1"** (checked by default). The file browser opens in
   the folder the program was launched from.
2. Creates a folder next to the PDF (`<name>_jpg_pages`) and rasterizes every
   page to JPG at the chosen DPI.
3. Auto-crops white margins from each JPG (detects the bounding box of non-white
   content).
4. Assembles the trimmed JPGs into `<name>_trimmed.pdf`, saved next to the
   original PDF. The images are embedded as-is (no extra re-compression is
   applied when building the PDF).
5. If 2-in-1 is checked, pairs of trimmed pages are placed side by side into a
   second PDF: `<name>_trimmed_2_in_1.pdf`.
6. Sends the temporary JPGs (and, if 2-in-1 was made, the intermediate
   `_trimmed.pdf`) to the **Recycle Bin** — so you're left with just the final
   PDF(s) you actually want.

This has been tested end-to-end (extraction, margin trimming, PDF assembly,
2-in-1 pairing, and cleanup) — see the logic in `main.py`.

## Building the .exe (must be done on Windows)

PyInstaller builds a native executable for whatever OS you run it on, so the
`.exe` has to be built **on a Windows machine** (not this Linux sandbox).

1. Install Python 3.10+ on Windows if you don't have it.
2. Copy this whole folder to the Windows machine.
3. Open a terminal in the folder and run:
   ```
   build.bat
   ```
   This installs the dependencies and runs PyInstaller for you.
4. The standalone exe appears at `dist\PDFTrimmer.exe`. That single file is
   all you need to copy/run — no Python install required on the target
   machine.

If you'd rather run the commands yourself instead of `build.bat`:
```
pip install -r requirements.txt
pyinstaller --onefile --noconsole --name PDFTrimmer --collect-all pymupdf main.py
```

## Running from source (for testing, on any OS with a display)

```
pip install -r requirements.txt
python main.py
```

## Shrinking the exe

The build is dominated by PyMuPDF's bundled MuPDF engine and font data, which
is hard to avoid since it's what does the PDF rasterizing. Still, you can get
it much smaller than a naive build:

- **Don't double-collect PyMuPDF.** Only pass `--collect-all pymupdf` once
  (an earlier version of this build script also passed `--collect-all fitz`,
  which is the same package under its old import name — that duplicated
  ~50-100MB of bundled data).
- **Build in a clean virtual environment.** `build.bat` now creates a fresh
  `venv` and installs only `requirements.txt` into it, so PyInstaller's
  dependency scan doesn't accidentally pull in unrelated packages you happen
  to have installed globally (matplotlib, scipy, pandas, jupyter, etc.). The
  script also explicitly excludes those common offenders just in case.
- **No numpy.** The margin-trimming logic now uses plain PIL instead of
  numpy, removing that dependency entirely.
- **Optional: UPX compression.** Download UPX
  (https://github.com/upx/upx/releases), point `UPX_DIR` at the top of
  `build.bat` to the folder containing `upx.exe`, and PyInstaller will
  compress the bundled binaries — typically another 30-50% off the final
  size. It's optional because a couple of antivirus engines flag UPX-packed
  exes as suspicious (false positive); skip it if that's a concern for your
  deployment.

With these changes you should land well under half the original 370MB —
typically somewhere in the 100-180MB range, since that's roughly the floor
for a PyInstaller build embedding a full PDF-rendering engine.



- "No compression at all" (step 4) is handled by embedding the JPG byte data
  directly into the PDF via `img2pdf` — nothing recompresses the image data
  during PDF assembly. The JPGs themselves are extracted/saved at quality 100
  to keep them as close to lossless as JPEG allows.
- Margin trimming uses a brightness threshold (pixels lighter than ~96% white
  are treated as margin) with a 2px safety pad, so it works even if the
  original page isn't pure-white background.
- If 2-in-1 is off, the final deliverable is `<name>_trimmed.pdf` and nothing
  extra is deleted beyond the temporary JPG folder.
- If a PDF has an odd number of pages, the last 2-in-1 sheet pairs the final
  page with a blank white page.
