// All dimensions passed to the driver are device pixels. Preserve the physical page origin.
using System;
using System.IO;
using System.Runtime.InteropServices;

public static class CheckedPrint {
    [StructLayout(LayoutKind.Sequential, CharSet=CharSet.Unicode)]
    struct Doc { public int size; public string name, output, type; public int flags; }
    [DllImport("kernel32")] static extern IntPtr GlobalLock(IntPtr h);
    [DllImport("kernel32")] static extern bool GlobalUnlock(IntPtr h);
    [DllImport("kernel32")] static extern IntPtr GlobalFree(IntPtr h);
    [DllImport("gdi32", CharSet=CharSet.Unicode)] static extern IntPtr CreateDC(string driver,string name,string port,IntPtr mode);
    [DllImport("gdi32", CharSet=CharSet.Unicode)] static extern int StartDoc(IntPtr dc,ref Doc doc);
    [DllImport("gdi32")] static extern int StartPage(IntPtr dc);
    [DllImport("gdi32")] static extern int EndPage(IntPtr dc);
    [DllImport("gdi32")] static extern int EndDoc(IntPtr dc);
    [DllImport("gdi32")] static extern int AbortDoc(IntPtr dc);
    [DllImport("gdi32")] static extern bool DeleteDC(IntPtr dc);
    [DllImport("gdi32")] static extern int GetDeviceCaps(IntPtr dc,int index);
    [DllImport("gdi32")] static extern int StretchDIBits(IntPtr dc,int x,int y,int w,int h,int sx,int sy,int sw,int sh,
        IntPtr pixels,IntPtr info,uint usage,uint rop);

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

    public static int Begin(IntPtr dc) {
        Doc doc=new Doc(); doc.size=Marshal.SizeOf(doc); doc.name="Voucher print job";
        return Check(StartDoc(dc,ref doc));
    }

    public static void Page(IntPtr dc,string path,int paperWidth,int paperHeight) {
        if (new FileInfo(path).Length > 256L*1024*1024) throw new IOException("Rendered page too large.");
        byte[] bmp=File.ReadAllBytes(path);
        if (bmp.Length<54 || bmp[0]!=66 || bmp[1]!=77 || BitConverter.ToInt32(bmp,14)!=40 ||
            BitConverter.ToInt16(bmp,26)!=1 || BitConverter.ToInt16(bmp,28)!=24 || BitConverter.ToInt32(bmp,30)!=0)
            throw new IOException("Unexpected rendered page format.");
        int offset=BitConverter.ToInt32(bmp,10), w=BitConverter.ToInt32(bmp,18), h=BitConverter.ToInt32(bmp,22);
        if (w<=0 || h<=0 || Math.Abs(w-paperWidth*6)>5 || Math.Abs(h-paperHeight*6)>5 || offset<54 ||
            offset + ((3L*w+3)/4*4)*h != bmp.LongLength) throw new IOException("Incomplete or mismatched rendered page.");
        int dw=(int)Math.Round(w*GetDeviceCaps(dc,88)/600.0), dh=(int)Math.Round(h*GetDeviceCaps(dc,90)/600.0);
        var buffer=GCHandle.Alloc(bmp,GCHandleType.Pinned);
        try {
            Check(StartPage(dc));
            IntPtr start=buffer.AddrOfPinnedObject();
            Check(StretchDIBits(dc,-GetDeviceCaps(dc,112),-GetDeviceCaps(dc,113),dw,dh,0,0,w,h,
                                IntPtr.Add(start,offset),IntPtr.Add(start,14),0,0x00CC0020));
            Check(EndPage(dc));
        } finally { buffer.Free(); }
    }

    public static void Finish(IntPtr dc) { Check(EndDoc(dc)); }
    public static void Close(IntPtr dc,bool finished) { if (!finished) AbortDoc(dc); DeleteDC(dc); }
}
