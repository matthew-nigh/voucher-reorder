// SPDX-License-Identifier: GPL-3.0-or-later
using System;
using System.Runtime.InteropServices;

public static class SettingsIdentity
{
    public const string AppId = "VoucherReorder.Settings";
    private static readonly Guid PropertyStoreId = new Guid("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99");

    [StructLayout(LayoutKind.Sequential)]
    private struct PropertyKey
    {
        public Guid FormatId;
        public uint PropertyId;
    }

    [StructLayout(LayoutKind.Explicit, Size = 24)]
    private struct PropVariant
    {
        [FieldOffset(0)] public ushort Type;
        [FieldOffset(8)] public IntPtr Value;
    }

    [ComImport, Guid("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    private interface IPropertyStore
    {
        void GetCount(out uint count);
        void GetAt(uint index, out PropertyKey key);
        void GetValue(ref PropertyKey key, out PropVariant value);
        void SetValue(ref PropertyKey key, ref PropVariant value);
        void Commit();
    }

    [DllImport("shell32.dll", PreserveSig = false)]
    private static extern void SHGetPropertyStoreForWindow(IntPtr window, ref Guid interfaceId,
        [MarshalAs(UnmanagedType.Interface)] out IPropertyStore store);

    [DllImport("shell32.dll", CharSet = CharSet.Unicode, PreserveSig = false)]
    private static extern void SHGetPropertyStoreFromParsingName(string path, IntPtr bindContext,
        uint flags, ref Guid interfaceId, [MarshalAs(UnmanagedType.Interface)] out IPropertyStore store);

    [DllImport("ole32.dll")]
    private static extern int PropVariantClear(ref PropVariant value);

    private static void SetAppId(IPropertyStore store)
    {
        var key = new PropertyKey {
            FormatId = new Guid("9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3"),
            PropertyId = 5
        };
        var value = new PropVariant { Type = 31, Value = Marshal.StringToCoTaskMemUni(AppId) };
        try {
            store.SetValue(ref key, ref value);
            store.Commit();
        } finally {
            PropVariantClear(ref value);
        }
    }

    public static void SetWindowAppId(IntPtr window)
    {
        IPropertyStore store;
        var interfaceId = PropertyStoreId;
        SHGetPropertyStoreForWindow(window, ref interfaceId, out store);
        try { SetAppId(store); }
        finally { Marshal.ReleaseComObject(store); }
    }

    public static void SetShortcutAppId(string path)
    {
        IPropertyStore store;
        var interfaceId = PropertyStoreId;
        // GPS_READWRITE asks the shell's .lnk property handler for a writable store.
        SHGetPropertyStoreFromParsingName(path, IntPtr.Zero, 2, ref interfaceId, out store);
        try { SetAppId(store); }
        finally { Marshal.ReleaseComObject(store); }
    }
}
