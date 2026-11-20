"""Vector-only band imposition, with clipped reusable PDF Form XObjects."""
from pathlib import Path
from pypdf import PdfReader, PdfWriter, Transformation
from pypdf.generic import (
    ArrayObject, BooleanObject, DecodedStreamObject, DictionaryObject,
    FloatObject, NameObject,
)
from .config import Settings


def reorder(source, destination: str | Path, settings: Settings) -> None:
    reader = PdfReader(source, strict=True)
    if reader.is_encrypted:
        raise ValueError("Encrypted print jobs are not supported.")
    if not reader.pages:
        raise ValueError("The print job has no pages.")
    normalized = PdfWriter(clone_from=reader)
    writer = PdfWriter()
    for page in normalized.pages:
        if float(page.get("/UserUnit", 1)) != 1:
            raise ValueError("Nonstandard PDF UserUnit is unsupported; print at normal scale.")
        if page.get("/Annots"):
            raise ValueError("Flatten annotations before sending a PDF print job.")
        page.transfer_rotation_to_content()
        # CropBox is the visible sheet, including non-zero origins.
        box = page.cropbox
        x0, y0 = float(box.left), float(box.bottom)
        width, height = float(box.width), float(box.height)
        if width <= 0 or height <= 0:
            raise ValueError("Page dimensions must be positive.")
        edges = settings.edges(height)
        page.add_transformation(Transformation().translate(-x0, -y0))
        form = DecodedStreamObject()
        contents = page.get_contents()
        form.set_data(contents.get_data() if contents is not None else b"")
        form.update({
            NameObject("/Type"): NameObject("/XObject"),
            NameObject("/Subtype"): NameObject("/Form"),
            NameObject("/BBox"): ArrayObject([FloatObject(n) for n in (0, 0, width, height)]),
            NameObject("/Resources"): page.get("/Resources", DictionaryObject()).clone(writer),
        })
        if "/Group" in page:
            form[NameObject("/Group")] = page["/Group"].clone(writer)
        ref = writer._add_object(form)
        out = writer.add_blank_page(width, height)
        out[NameObject("/Resources")] = DictionaryObject({NameObject("/XObject"):
            DictionaryObject({NameObject("/Sheet"): ref})})
        commands = []
        top = 0.0
        for source_index in settings.order:
            band_height = edges[source_index + 1] - edges[source_index]
            source_bottom = height - edges[source_index + 1]
            target_bottom = height - top - band_height
            dx, dy = (float(n) * 72 for n in settings.offsets[source_index])
            # Outer clip fixes the destination slot; inner clip selects original band.
            # Nudges move content inside the slot without leaking into another check stub.
            commands.append(
                f"q 0 {target_bottom:.9f} {width:.9f} {band_height:.9f} re W n "
                f"1 0 0 1 {dx:.9f} {target_bottom-source_bottom-dy:.9f} cm "
                f"0 {source_bottom:.9f} {width:.9f} {band_height:.9f} re W n /Sheet Do Q\n"
            )
            top += band_height
        stream = DecodedStreamObject()
        stream.set_data("".join(commands).encode("ascii"))
        out[NameObject("/Contents")] = writer._add_object(stream)
    writer._root_object[NameObject("/ViewerPreferences")] = DictionaryObject({
        NameObject("/PrintScaling"): NameObject("/None"),
        NameObject("/Duplex"): NameObject("/Simplex"),
        NameObject("/PickTrayByPDFSize"): BooleanObject(True),
    })
    writer.add_metadata({"/Producer": "Voucher Reorder", "/Title": "Voucher print job"})
    with open(destination, "wb") as output:
        writer.write(output)
