# Require the driver to spool RAW PostScript rather than intermediate EMF.
Add-Type -TypeDefinition @'
using System;
using System.ComponentModel;
using System.Runtime.InteropServices;
public static class RawQueue {
    [StructLayout(LayoutKind.Sequential)] struct Defaults { public IntPtr type, mode; public uint access; }
    [StructLayout(LayoutKind.Sequential)] struct Info { public IntPtr name, port; public uint attributes, deviceTimeout, retryTimeout; }
    [DllImport("winspool.drv",CharSet=CharSet.Unicode,SetLastError=true)] static extern bool OpenPrinter(string name,out IntPtr handle,ref Defaults defaults);
    [DllImport("winspool.drv",CharSet=CharSet.Unicode,SetLastError=true)] static extern bool GetPrinter(IntPtr handle,uint level,IntPtr buf,uint size,out uint needed);
    [DllImport("winspool.drv",CharSet=CharSet.Unicode,SetLastError=true)] static extern bool SetPrinter(IntPtr handle,uint level,ref Info info,uint command);
    [DllImport("winspool.drv")] static extern bool ClosePrinter(IntPtr handle);
    public static void Configure() {
        Defaults defaults=new Defaults(); defaults.access=0xC;
        IntPtr h;
        if (!OpenPrinter("Voucher Reorder",out h,ref defaults)) throw new Win32Exception();
        try {
            uint size;
            GetPrinter(h,5,IntPtr.Zero,0,out size);
            if (size==0 || size>1048576) throw new Win32Exception();
            IntPtr buf=Marshal.AllocHGlobal((int)size);
            try {
                if (!GetPrinter(h,5,buf,size,out size)) throw new Win32Exception();
                Info info=(Info)Marshal.PtrToStructure(buf,typeof(Info));
                info.attributes |= 0x1000; // PRINTER_ATTRIBUTE_RAW_ONLY
                if (!SetPrinter(h,5,ref info,0)) throw new Win32Exception();
            } finally { Marshal.FreeHGlobal(buf); }
        } finally { ClosePrinter(h); }
    }
}
'@
[RawQueue]::Configure()
