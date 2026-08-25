"""
PDF Trimmer / 2-in-1 tool
--------------------------
1) Shows a pop-up to pick a PDF, set DPI (default 300) and toggle "2 pages -> 1 page"
   (default checked). File browser opens in the folder the program was launched from.
2) Creates a folder next to the PDF and rasterizes every page to JPG at the chosen DPI.
3) Auto-crops (removes) white margins from every JPG.
4) Combines all trimmed JPGs into a new, uncompressed-assembly PDF named
   "<original>_trimmed.pdf" saved next to the original PDF.
5) If "2 pages -> 1" is checked, pairs of trimmed pages are combined side-by-side into a
   second PDF named "<original>_trimmed_2_in_1.pdf".
6) Sends the extracted/trimmed JPGs (and, if 2-in-1 was made, the intermediate
   "_trimmed.pdf") to the Recycle Bin, keeping only the final deliverable.
"""

import os
import sys
import threading
import traceback

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import pymupdf as fitz  # PyMuPDF
from PIL import Image
import img2pdf
from send2trash import send2trash


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def get_start_dir() -> str:
    """Best-effort guess of 'the folder the program was called from'."""
    cwd = os.getcwd()
    if os.path.isdir(cwd):
        return cwd
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def trim_white_margins(img: Image.Image, tolerance: int = 245) -> Image.Image:
    """Crop away white (or near-white) borders around the page content."""
    rgb = img.convert("RGB")
    gray = rgb.convert("L")
    # Build a binary mask: 255 where there is content, 0 where it's background.
    mask = gray.point(lambda p: 255 if p < tolerance else 0)
    bbox = mask.getbbox()
    if not bbox:
        return rgb

    pad = 2  # tiny safety margin so we don't clip anti-aliased edges
    x0, y0, x1, y1 = bbox
    x0 = max(0, x0 - pad)
    y0 = max(0, y0 - pad)
    x1 = min(rgb.width, x1 + pad)
    y1 = min(rgb.height, y1 + pad)
    return rgb.crop((x0, y0, x1, y1))


def combine_two_pages(img1: Image.Image, img2: Image.Image) -> Image.Image:
    """Place two page images side by side on one landscape page."""
    target_h = max(img1.height, img2.height)

    def scale_to_height(im: Image.Image, h: int) -> Image.Image:
        if im.height == h:
            return im
        w = max(1, int(im.width * (h / im.height)))
        return im.resize((w, h), Image.LANCZOS)

    im1 = scale_to_height(img1, target_h)
    im2 = scale_to_height(img2, target_h)

    gap = max(10, target_h // 100)
    total_w = im1.width + im2.width + gap
    canvas = Image.new("RGB", (total_w, target_h), "white")
    canvas.paste(im1, (0, 0))
    canvas.paste(im2, (im1.width + gap, 0))
    return canvas


# --------------------------------------------------------------------------- #
# Core pipeline
# --------------------------------------------------------------------------- #

def run_pipeline(pdf_path: str, dpi: int, jpeg_quality: int, two_in_one: bool, progress_cb=None) -> str:
    def report(value, maximum, text):
        if progress_cb:
            progress_cb(value, maximum, text)

    base_dir = os.path.dirname(os.path.abspath(pdf_path))
    pdf_name = os.path.splitext(os.path.basename(pdf_path))[0]

    extract_folder = os.path.join(base_dir, f"{pdf_name}_jpg_pages")
    os.makedirs(extract_folder, exist_ok=True)

    # --- Step 2: extract pages to JPG at chosen DPI ------------------------ #
    doc = fitz.open(pdf_path)
    n_pages = doc.page_count
    zoom = dpi / 72.0
    mat = fitz.Matrix(zoom, zoom)

    jpg_paths = []
    for i, page in enumerate(doc):
        report(i, n_pages * 3, f"Extracting page {i + 1}/{n_pages}")
        pix = page.get_pixmap(matrix=mat, alpha=False)
        jpg_path = os.path.join(extract_folder, f"{pdf_name}_{i + 1:04d}.jpg")
        pix.save(jpg_path, jpg_quality=jpeg_quality)
        jpg_paths.append(jpg_path)
    doc.close()

    # --- Step 3: trim white margins ---------------------------------------- #
    trimmed_paths = []
    for i, path in enumerate(jpg_paths):
        report(n_pages + i, n_pages * 3, f"Trimming page {i + 1}/{n_pages}")
        img = Image.open(path)
        trimmed = trim_white_margins(img)
        trimmed.save(path, quality=100, dpi=(dpi, dpi))
        trimmed_paths.append(path)

    # --- Step 4: combine JPGs into a PDF (images embedded as-is, no re-compression) --- #
    report(n_pages * 2, n_pages * 3, "Building trimmed PDF")
    trimmed_pdf_path = os.path.join(base_dir, f"{pdf_name}_trimmed.pdf")
    with open(trimmed_pdf_path, "wb") as f:
        f.write(img2pdf.convert(trimmed_paths))

    final_path = trimmed_pdf_path

    # --- Step 5: 2 pages -> 1 page ------------------------------------------ #
    two_in_one_pdf_path = None
    if two_in_one:
        report(n_pages * 2, n_pages * 3, "Combining pages 2-in-1")
        combined_dir = os.path.join(extract_folder, "_combined_2in1")
        os.makedirs(combined_dir, exist_ok=True)

        combined_paths = []
        for idx in range(0, len(trimmed_paths), 2):
            img1 = Image.open(trimmed_paths[idx])
            if idx + 1 < len(trimmed_paths):
                img2 = Image.open(trimmed_paths[idx + 1])
            else:
                img2 = Image.new("RGB", img1.size, "white")
            combined = combine_two_pages(img1, img2)
            out_path = os.path.join(combined_dir, f"{pdf_name}_2in1_{idx // 2 + 1:04d}.jpg")
            combined.save(out_path, quality=100, dpi=(dpi, dpi))
            combined_paths.append(out_path)

        two_in_one_pdf_path = os.path.join(base_dir, f"{pdf_name}_trimmed_2_in_1.pdf")
        with open(two_in_one_pdf_path, "wb") as f:
            f.write(img2pdf.convert(combined_paths))
        final_path = two_in_one_pdf_path

    # --- Step 6: clean-up (Recycle Bin) ------------------------------------- #
    report(n_pages * 3, n_pages * 3, "Cleaning up")
    try:
        send2trash(extract_folder)  # removes all extracted/trimmed/combined jpgs
    except Exception:
        pass

    if two_in_one and two_in_one_pdf_path and os.path.isfile(trimmed_pdf_path):
        try:
            send2trash(trimmed_pdf_path)
        except Exception:
            pass

    return final_path


# --------------------------------------------------------------------------- #
# GUI
# --------------------------------------------------------------------------- #

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("PDF Trimmer / 2-in-1")
        self.resizable(False, False)

        self.pdf_path = tk.StringVar()
        self.dpi = tk.StringVar(value="300")
        self.jpeg_quality = tk.StringVar(value="98")
        self.two_in_one = tk.BooleanVar(value=True)
        self.start_dir = get_start_dir()

        pad = {"padx": 10, "pady": 6}

        frm = ttk.Frame(self)
        frm.pack(fill="both", expand=True, padx=10, pady=10)

        ttk.Label(frm, text="PDF file:").grid(row=0, column=0, sticky="w", **pad)
        ttk.Entry(frm, textvariable=self.pdf_path, width=52).grid(
            row=1, column=0, columnspan=2, sticky="we", padx=10
        )
        ttk.Button(frm, text="Browse...", command=self.browse).grid(row=1, column=2, padx=10)

        ttk.Label(frm, text="DPI:").grid(row=2, column=0, sticky="w", **pad)
        ttk.Entry(frm, textvariable=self.dpi, width=10).grid(row=2, column=1, sticky="w", **pad)

        ttk.Label(frm, text="JPG Quality(0-100: 98 is close to lossless.):").grid(row=3, column=0, sticky="w", **pad)
        ttk.Entry(frm, textvariable=self.jpeg_quality, width=10).grid(row=3, column=1, sticky="w", **pad)

        ttk.Checkbutton(
            frm, text="Combine 2 pages into 1", variable=self.two_in_one
        ).grid(row=4, column=0, columnspan=2, sticky="w", **pad)

        btns = ttk.Frame(frm)
        btns.grid(row=5, column=0, columnspan=3, pady=(10, 0))
        self.run_btn = ttk.Button(btns, text="Run", command=self.on_run)
        self.run_btn.pack(side="left", padx=5)
        ttk.Button(btns, text="Cancel", command=self.destroy).pack(side="left", padx=5)

        self.progress = ttk.Progressbar(frm, mode="determinate", length=400)
        self.progress.grid(row=6, column=0, columnspan=3, pady=(12, 0))
        self.status = ttk.Label(frm, text="")
        self.status.grid(row=7, column=0, columnspan=3, sticky="w", padx=10)

    def browse(self):
        path = filedialog.askopenfilename(
            title="Select PDF file",
            initialdir=self.start_dir,
            filetypes=[("PDF files", "*.pdf")],
        )
        if path:
            self.pdf_path.set(path)

    def set_status(self, text: str):
        self.status.config(text=text)
        self.update_idletasks()

    def on_run(self):
        pdf_path = self.pdf_path.get().strip()
        if not pdf_path or not os.path.isfile(pdf_path):
            messagebox.showerror("Error", "Please select a valid PDF file.")
            return
        try:
            dpi = int(self.dpi.get().strip())
            if dpi <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Error", "DPI must be a positive whole number.")
            return

        try:
            jpeg_quality = int(self.jpeg_quality.get().strip())
            if jpeg_quality <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Error", "JPEG Quality must be a positive whole number.")
            return

        two_in_one = self.two_in_one.get()
        self.run_btn.config(state="disabled")
        self.set_status("Processing...")

        thread = threading.Thread(
            target=self.process, args=(pdf_path, dpi, jpeg_quality,two_in_one), daemon=True
        )
        thread.start()

    def process(self, pdf_path, dpi, jpeg_quality,two_in_one):
        try:
            result_path = run_pipeline(pdf_path, dpi, jpeg_quality,two_in_one, progress_cb=self.report_progress)
            self.after(0, lambda: self.finish_ok(result_path))
        except Exception as e:
            tb = traceback.format_exc()
            self.after(0, lambda: self.finish_error(str(e), tb))

    def report_progress(self, value, maximum, text):
        def upd():
            self.progress["maximum"] = max(1, maximum)
            self.progress["value"] = value
            self.set_status(text)

        self.after(0, upd)

    def finish_ok(self, result_path):
        self.set_status("Done.")
        messagebox.showinfo("Done", f"Created:\n{result_path}")
        self.destroy()

    def finish_error(self, msg, tb):
        self.set_status("Error.")
        print(tb)
        messagebox.showerror("Error", msg)
        self.run_btn.config(state="normal")


if __name__ == "__main__":
    app = App()
    app.mainloop()
