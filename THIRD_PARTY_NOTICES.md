# Third-party licenses and source distribution

Voucher Reorder's own code is **GPL-3.0-or-later**. The components below remain
under their upstream terms; the project does not relicense them. No commercial
Ghostscript, proprietary PDF printer, RedMon binary or custom driver is bundled.
Dependency versions, URLs and SHA-256 checksums are in
[`packaging/dependencies.json`](packaging/dependencies.json).

## Distributed application components

| Component | Version | License / role |
| --- | --- | --- |
| CPython embeddable x64 | 3.13.12 | PSF-2.0 and historical Python notices; interpreter and standard library |
| pypdf | 7.1.1 | BSD-3-Clause; PDF object/resource manipulation |
| Ghostscript | 10.08.0 | AGPL-3.0-or-later; separate, unmodified PostScript-to-PDF executable |
| NSIS installer stubs/plugins | 3.11 or newer | zlib/libpng license; installer only. NSIS build-tool components have additional terms in `NSIS-COPYING.txt` |

GPLv3 and AGPLv3 have explicit section-13 interoperability; **AGPL-covered parts
remain AGPL-covered**, not GPL-only. See the [GNU license compatibility explanation](https://www.gnu.org/licenses/gpl-faq.html#v3Notwithstanding).
All application code and bundled copyleft component sources are delivered together.
These executables are invoked locally through ordinary command lines and files;
Voucher Reorder exposes no remote document-processing service.

The installer contains `licenses/`, populated from **all** upstream source files
named license/licence/copying/copyright/notice, retaining their source-relative
paths. `vendor/ghostscript/doc` retains upstream documentation. This preserves the
actual notices rather than replacing them with this summary. The original source
archives accompany every installer in `VoucherReorder-0.2.0-sources.zip`.

Relevant transitive components include:

- CPython: OpenSSL (Apache-2.0), libffi (MIT), zlib (zlib), SQLite (public domain),
  and other standard-library notices in Python's original LICENSE. The official
  runtime's Microsoft runtime DLLs are system/compiler runtime components, not
  GPL-licensed application libraries.
- Ghostscript: bundled FreeType (FreeType license alternative), font resources,
  libjpeg (IJG), libpng (libpng), zlib, OpenJPEG (BSD), Little CMS (MIT), jbig2dec
  (AGPL), expat (MIT), and related upstream notices retained in its source archive.
## Microsoft platform dependencies (not open-source application components)

Windows, PowerShell/WinForms, the Microsoft PostScript driver and the print spooler
are installed operating-system components; **not redistributed here**. CPython's
official distribution includes its customary Microsoft C runtime DLLs, which fall
under the GPL's system/compiler-runtime provisions, not a claim that Microsoft's
license is GPL-compatible. Keep Python's official distribution notices intact.

Ghostscript additionally needs the Microsoft Visual C++ x64 runtime. Its separate
proprietary `vcredist_x64.exe` is **excluded** from our package. Optional elevated virtual-printer setup obtains it
from Microsoft's official endpoint only when missing, checks a valid Microsoft
Authenticode signature, and installs it as a shared system prerequisite. Microsoft
terms apply to that prerequisite; it is not relicensed by this project. See
[Microsoft's redistribution documentation](https://learn.microsoft.com/en-us/cpp/windows/redistributing-visual-cpp-files).
The shared runtime and OS driver are left installed on uninstall. PDF handoff never
invokes Ghostscript or installs this prerequisite; it uses the packaged Python runtime and the Windows PDF renderer.

## Source availability and reproducing modifications

Always distribute these three files together, in the same downloadable artifact or
Release: `VoucherReorder-0.2.0-Setup.exe`, `VoucherReorder-0.2.0-sources.zip`, and
`SHA256SUMS.txt`. **Do not distribute only the executable and rely on an upstream
URL as the corresponding-source offer.** Our workflow uploads/releases all three.
The source ZIP includes this application's build/install scripts, tests, license,
metadata and documents, plus the exact original CPython, pypdf and Ghostscript source archives. `BUILD_INFO.json` records upstream hashes and revision.

The distributed Python code is already its preferred source form. To replace a
component, unpack its source archive, follow its included build instructions, then
substitute its build products in the staging directory before compiling NSIS:

- CPython: source `PCbuild/readme.txt` (Windows build) and LICENSE.
- Ghostscript: source `doc/src/Make.rst` and Windows makefiles under `psi/`.
- pypdf: source `pyproject.toml`; pure Python with no compiled engine.

No upstream code is patched by the packaging process. Reproducing an identical
upstream signed binary is not claimed; these sources permit modifying and rebuilding
the components. Before publishing a modified build, recheck its full dependency
notices, source completeness and hashes. Network-facing changes to AGPL components
also require review of their network-source obligations.

## Development-only tools

pytest (MIT), ReportLab (BSD), PyMuPDF (AGPL), Ruff (MIT), 7-Zip (LGPL/BSD/unRAR
build-tool terms), GitHub Actions and the NSIS compiler are not shipped as runtime
application dependencies. PyMuPDF is only a test renderer. The bundled NSIS
executable stubs/plugins are covered above. No test-generated financial data is real.
