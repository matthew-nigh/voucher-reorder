// PDFium's EMF print mode preserves paths/text. Reject any raster fallback before submission.
using System;
using System.IO;
using System.Text;
using System.Runtime.InteropServices;

public static class CheckedPrint {
    [StructLayout(LayoutKind.Sequential, CharSet=CharSet.Unicode)]
    struct Doc { public int size; public string name, output, type; public int flags; }
    [StructLayout(LayoutKind.Sequential)]
    struct Rect { public int left, top, right, bottom; }
    [DllImport("kernel32")] static extern IntPtr GlobalLock(IntPtr h);
    [DllImport("kernel32")] static extern bool GlobalUnlock(IntPtr h);
    [DllImport("kernel32")] static extern IntPtr GlobalFree(IntPtr h);
    [DllImport("kernel32", CharSet=CharSet.Unicode)] static extern IntPtr LoadLibraryEx(string path,IntPtr file,uint flags);
    [DllImport("gdi32", CharSet=CharSet.Unicode)] static extern IntPtr CreateDC(string driver,string name,string port,IntPtr mode);
    [DllImport("gdi32", CharSet=CharSet.Unicode)] static extern int StartDoc(IntPtr dc,ref Doc doc);
    [DllImport("gdi32")] static extern int StartPage(IntPtr dc);
    [DllImport("gdi32")] static extern int EndPage(IntPtr dc);
    [DllImport("gdi32")] static extern int EndDoc(IntPtr dc);
    [DllImport("gdi32")] static extern int AbortDoc(IntPtr dc);
    [DllImport("gdi32")] static extern bool DeleteDC(IntPtr dc);
    [DllImport("gdi32")] static extern int GetDeviceCaps(IntPtr dc,int index);
    [DllImport("gdi32", CharSet=CharSet.Unicode)] static extern IntPtr CreateEnhMetaFile(IntPtr dc,string file,ref Rect frame,string description);
    [DllImport("gdi32")] static extern IntPtr CloseEnhMetaFile(IntPtr dc);
    [DllImport("gdi32")] static extern bool DeleteEnhMetaFile(IntPtr emf);
    [DllImport("gdi32")] static extern uint GetEnhMetaFileBits(IntPtr emf,uint size,IntPtr buffer);
    delegate int RecordProc(IntPtr dc,IntPtr table,IntPtr record,int count,IntPtr data);
    [DllImport("gdi32")] static extern bool EnumEnhMetaFile(IntPtr dc,IntPtr emf,RecordProc callback,IntPtr data,ref Rect rect);
    [DllImport("gdi32")] static extern bool PlayEnhMetaFile(IntPtr dc,IntPtr emf,ref Rect rect);
    [DllImport("pdfium", CallingConvention=CallingConvention.Cdecl)] static extern void FPDF_InitLibrary();
    [DllImport("pdfium", CallingConvention=CallingConvention.Cdecl)] static extern void FPDF_DestroyLibrary();
    [DllImport("pdfium", CallingConvention=CallingConvention.Cdecl)] static extern int FPDF_SetPrintMode(int mode);
    [DllImport("pdfium", CallingConvention=CallingConvention.Cdecl)] static extern IntPtr FPDF_LoadDocument(byte[] path,IntPtr password);
    [DllImport("pdfium", CallingConvention=CallingConvention.Cdecl)] static extern void FPDF_CloseDocument(IntPtr doc);
    [DllImport("pdfium", CallingConvention=CallingConvention.Cdecl)] static extern int FPDF_GetPageCount(IntPtr doc);
    [DllImport("pdfium", CallingConvention=CallingConvention.Cdecl)] static extern IntPtr FPDF_LoadPage(IntPtr doc,int index);
    [DllImport("pdfium", CallingConvention=CallingConvention.Cdecl)] static extern void FPDF_ClosePage(IntPtr page);
    [DllImport("pdfium", CallingConvention=CallingConvention.Cdecl)] static extern double FPDF_GetPageWidth(IntPtr page);
    [DllImport("pdfium", CallingConvention=CallingConvention.Cdecl)] static extern double FPDF_GetPageHeight(IntPtr page);
    [DllImport("pdfium", CallingConvention=CallingConvention.Cdecl)] static extern int FPDF_RenderPage(IntPtr dc,IntPtr page,int x,int y,int w,int h,int rotation,int flags);

    static int Check(int result) {
        if (result <= 0) throw new IOException("Printer rejected the document or page.");
        return result;
    }
    public static IntPtr Open(string printer,IntPtr mode) {
        IntPtr ptr=GlobalLock(mode);
        if (ptr==IntPtr.Zero) throw new IOException("Unavailable printer configuration.");
        try {
            IntPtr dc=CreateDC("WINSPOOL",printer,null,ptr);
            if (dc==IntPtr.Zero) throw new IOException("Cannot open the selected printer.");
            return dc;
        } finally { GlobalUnlock(mode); GlobalFree(mode); }
    }

    static IntPtr VectorPage(IntPtr dc,IntPtr doc,int index,int width,int height) {
        IntPtr page=FPDF_LoadPage(doc,index);
        if (page==IntPtr.Zero) throw new IOException("PDFium could not load a page.");
        IntPtr recording=IntPtr.Zero, emf=IntPtr.Zero;
        try {
            if (Math.Abs(FPDF_GetPageWidth(page)-width*0.72)>0.75 ||
                Math.Abs(FPDF_GetPageHeight(page)-height*0.72)>0.75)
                throw new IOException("PDFium page dimensions differ from selected paper.");
            Rect frame=new Rect(); frame.right=(int)Math.Round(width*25.4); frame.bottom=(int)Math.Round(height*25.4);
            recording=CreateEnhMetaFile(dc,null,ref frame,null);
            if (recording==IntPtr.Zero) throw new IOException("Cannot record vector page.");
            int w=(int)Math.Round(width*GetDeviceCaps(dc,88)/100.0);
            int h=(int)Math.Round(height*GetDeviceCaps(dc,90)/100.0);
            // FPDF_PRINTING | FPDF_ANNOT. EMF mode uses GDI paths/text, not a render bitmap.
            if (FPDF_RenderPage(recording,page,0,0,w,h,0,0x800|1)==0)
                throw new IOException("PDFium vector rendering failed.");
            emf=CloseEnhMetaFile(recording); recording=IntPtr.Zero;
            if (emf==IntPtr.Zero || GetEnhMetaFileBits(emf,0,IntPtr.Zero)>64*1024*1024)
                throw new IOException("Vector page unavailable or exceeds limit.");
            bool raster=false, marks=false;
            RecordProc inspect=delegate(IntPtr unused,IntPtr table,IntPtr record,int count,IntPtr data) {
                int kind=Marshal.ReadInt32(record);
                if ((kind>=76 && kind<=81) || kind==114 || kind==116) raster=true;
                if ((kind>=2 && kind<=8) || (kind>=42 && kind<=47) || (kind>=62 && kind<=64) ||
                    kind==83 || kind==84 || (kind>=85 && kind<=92) || kind==96 || kind==97) marks=true;
                return 1;
            };
            if (!EnumEnhMetaFile(IntPtr.Zero,emf,inspect,IntPtr.Zero,ref frame))
                throw new IOException("Cannot verify vector page.");
            GC.KeepAlive(inspect);
            if (raster) throw new IOException("PDF requires raster drawing; vector-only printing refused.");
            if (!marks) throw new IOException("Blank vector page refused.");
            IntPtr result=emf; emf=IntPtr.Zero; return result;
        } finally {
            if (recording!=IntPtr.Zero) DeleteEnhMetaFile(CloseEnhMetaFile(recording));
            if (emf!=IntPtr.Zero) DeleteEnhMetaFile(emf);
            FPDF_ClosePage(page);
        }
    }

    public static void Print(IntPtr dc,string library,string path,int pages,int width,int height) {
        // Load only the pinned DLL and system dependencies, never DLLs from the job directory.
        if (LoadLibraryEx(library,IntPtr.Zero,0x100|0x800)==IntPtr.Zero)
            throw new IOException("Cannot load bundled PDFium.");
        FPDF_InitLibrary();
        IntPtr doc=IntPtr.Zero;
        try {
            if (FPDF_SetPrintMode(0)==0) throw new IOException("Vector print mode unavailable.");
            doc=FPDF_LoadDocument(Encoding.UTF8.GetBytes(path+"\0"),IntPtr.Zero);
            if (doc==IntPtr.Zero || FPDF_GetPageCount(doc)!=pages) throw new IOException("PDFium page count mismatch.");
            // Preflight every page before starting a printer job; only one EMF is kept at a time.
            for (int i=0;i<pages;i++) DeleteEnhMetaFile(VectorPage(dc,doc,i,width,height));
            Doc job=new Doc(); job.size=Marshal.SizeOf(job); job.name="Voucher print job";
            int id=Check(StartDoc(dc,ref job));
            File.WriteAllText(Path.Combine(Path.GetDirectoryName(path),"windows-job-id"),id.ToString());
            for (int i=0;i<pages;i++) {
                IntPtr emf=VectorPage(dc,doc,i,width,height);
                try {
                    Rect target=new Rect();
                    target.left=-GetDeviceCaps(dc,112); target.top=-GetDeviceCaps(dc,113);
                    target.right=target.left+(int)Math.Round(width*GetDeviceCaps(dc,88)/100.0);
                    target.bottom=target.top+(int)Math.Round(height*GetDeviceCaps(dc,90)/100.0);
                    Check(StartPage(dc));
                    if (!PlayEnhMetaFile(dc,emf,ref target)) throw new IOException("Printer rejected vector page.");
                    Check(EndPage(dc));
                } finally { DeleteEnhMetaFile(emf); }
            }
            Check(EndDoc(dc));
        } finally {
            if (doc!=IntPtr.Zero) FPDF_CloseDocument(doc);
            FPDF_DestroyLibrary();
        }
    }
    public static void Close(IntPtr dc,bool finished) { if (!finished) AbortDoc(dc); DeleteDC(dc); }
}
