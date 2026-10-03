// WorthlessTask native launcher -- C# port, slice 1: the spoof window.
//
// The window is the part Discord actually reads, so it is ported first and with the
// exact contract the live A/B test proved on 2026-09-25:
//   * WS_CAPTION present, WS_EX_LAYERED absent (layered windows are ignored),
//   * WM_NCCALCSIZE returns 0 so the client owns the whole rect (browser trick),
//   * no blocking waits in the message loop.
//
// Build (the C# compiler ships with Windows, no SDK needed):
//   csc /nologo /target:winexe /platform:x64 /out:build\cs\worthlesstask.exe /reference:System.dll cs\Launcher.cs
//
// C# 5 only: the .NET Framework compiler that ships with Windows does not know
// string interpolation, expression-bodied members or `out var`.

using System;
using System.Runtime.InteropServices;

namespace WorthlessTask
{
    internal static class Native
    {
        internal const int WS_CAPTION = 0x00C00000;
        internal const int WS_THICKFRAME = 0x00040000;
        internal const int WS_MINIMIZEBOX = 0x00020000;
        internal const int WS_SYSMENU = 0x00080000;
        internal const int WS_VISIBLE = 0x10000000;
        internal const int WS_CLIPCHILDREN = 0x02000000;
        internal const int WS_CLIPSIBLINGS = 0x04000000;
        internal const int WS_EX_APPWINDOW = 0x00040000;

        internal const int WM_DESTROY = 0x0002;
        internal const int WM_PAINT = 0x000F;
        internal const int WM_CLOSE = 0x0010;
        internal const int WM_ERASEBKGND = 0x0014;
        internal const int WM_NCCALCSIZE = 0x0083;
        internal const int CS_HREDRAW = 0x0002;
        internal const int CS_VREDRAW = 0x0001;

        internal const int SRCCOPY = 0x00CC0020;
        internal const int TRANSPARENT = 1;
        internal const int DEFAULT_CHARSET = 1;
        internal const int CLEARTYPE_QUALITY = 5;
        internal const int DT_LEFT = 0x00000000;
        internal const int DT_CENTER = 0x00000001;
        internal const int DT_VCENTER = 0x00000004;
        internal const int DT_SINGLELINE = 0x00000020;
        internal const int DT_NOPREFIX = 0x00000800;
        internal const int GRADIENT_FILL_RECT_V = 0x00000001;
        internal const int BI_RGB = 0;
        internal const int DIB_RGB_COLORS = 0;
        internal const int NULL_BRUSH = 5;

        [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
        internal struct WNDCLASS
        {
            internal int style;
            internal IntPtr lpfnWndProc;
            internal int cbClsExtra;
            internal int cbWndExtra;
            internal IntPtr hInstance;
            internal IntPtr hIcon;
            internal IntPtr hCursor;
            internal IntPtr hbrBackground;
            internal IntPtr lpszMenuName;
            internal IntPtr lpszClassName;
        }

        [StructLayout(LayoutKind.Sequential)]
        internal struct MSG
        {
            internal IntPtr hwnd;
            internal int message;
            internal IntPtr wParam;
            internal IntPtr lParam;
            internal int time;
            internal POINT pt;
        }

        [StructLayout(LayoutKind.Sequential)]
        internal struct POINT { internal int X; internal int Y; }

        [StructLayout(LayoutKind.Sequential)]
        internal struct RECT
        {
            internal int Left, Top, Right, Bottom;
            internal int Width { get { return Right - Left; } }
            internal int Height { get { return Bottom - Top; } }
        }

        [StructLayout(LayoutKind.Sequential)]
        internal struct PAINTSTRUCT
        {
            internal IntPtr hdc;
            internal int fErase;
            internal RECT rcPaint;
            internal int fRestore;
            internal int fIncUpdate;
            [MarshalAs(UnmanagedType.ByValArray, SizeConst = 32)]
            internal byte[] rgbReserved;
        }

        [StructLayout(LayoutKind.Sequential)]
        internal struct TRIVERTEX
        {
            internal int x, y;
            internal short Red, Green, Blue, Alpha;
        }

        [StructLayout(LayoutKind.Sequential)]
        internal struct GRADIENT_RECT
        {
            internal uint UpperLeft, LowerRight;
        }

        [StructLayout(LayoutKind.Sequential)]
        internal struct BITMAPINFOHEADER
        {
            internal int biSize, biWidth, biHeight;
            internal short biPlanes, biBitCount;
            internal int biCompression, biSizeImage;
            internal int biXPelsPerMeter, biYPelsPerMeter, biClrUsed, biClrImportant;
        }

        [StructLayout(LayoutKind.Sequential)]
        internal struct BITMAPINFO
        {
            internal BITMAPINFOHEADER bmiHeader;
            internal uint bmiColors0, bmiColors1, bmiColors2;
        }

        internal delegate IntPtr WndProc(IntPtr hwnd, int msg, IntPtr wParam, IntPtr lParam);

        [DllImport("user32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        internal static extern ushort RegisterClassW(ref WNDCLASS lpwcx);
        [DllImport("user32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        internal static extern IntPtr CreateWindowExW(uint ex, string cls, string title, uint style,
            int x, int y, int w, int h, IntPtr parent, IntPtr menu, IntPtr instance, IntPtr param);
        [DllImport("user32.dll", CharSet = CharSet.Unicode)]
        internal static extern IntPtr DefWindowProcW(IntPtr h, int m, IntPtr w, IntPtr l);
        [DllImport("user32.dll")]
        internal static extern int GetMessageW(out MSG msg, IntPtr h, uint min, uint max);
        [DllImport("user32.dll")]
        internal static extern bool TranslateMessage(ref MSG msg);
        [DllImport("user32.dll")]
        internal static extern IntPtr DispatchMessageW(ref MSG msg);
        [DllImport("user32.dll")]
        internal static extern void PostQuitMessage(int code);
        [DllImport("user32.dll")]
        internal static extern IntPtr BeginPaint(IntPtr h, out PAINTSTRUCT ps);
        [DllImport("user32.dll")]
        internal static extern bool EndPaint(IntPtr h, ref PAINTSTRUCT ps);
        [DllImport("user32.dll")]
        internal static extern bool GetClientRect(IntPtr h, out RECT r);
        [DllImport("user32.dll")]
        internal static extern bool DestroyWindow(IntPtr h);
        [DllImport("user32.dll")]
        internal static extern bool ShowWindow(IntPtr h, int cmd);
        [DllImport("user32.dll")]
        internal static extern bool SetForegroundWindow(IntPtr h);
        [DllImport("user32.dll")]
        internal static extern IntPtr LoadCursorW(IntPtr h, IntPtr name);
        [DllImport("user32.dll", CharSet = CharSet.Unicode)]
        internal static extern int DrawTextW(IntPtr hdc, string text, int count, ref RECT rect, uint flags);
        [DllImport("user32.dll")]
        internal static extern bool SetWindowRgn(IntPtr h, IntPtr rgn, bool redraw);
        [DllImport("kernel32.dll", CharSet = CharSet.Unicode)]
        internal static extern IntPtr GetModuleHandleW(string name);

        [DllImport("gdi32.dll")]
        internal static extern IntPtr CreateSolidBrush(uint color);
        [DllImport("gdi32.dll")]
        internal static extern IntPtr CreateFontW(int h, int w, int esc, int orient, int weight,
            uint italic, uint underline, uint strike, uint charset, uint outp, uint clip, uint quality,
            uint pitch, string face);
        [DllImport("gdi32.dll")]
        internal static extern IntPtr SelectObject(IntPtr hdc, IntPtr obj);
        [DllImport("gdi32.dll")]
        internal static extern bool DeleteObject(IntPtr obj);
        [DllImport("gdi32.dll")]
        internal static extern int SetBkMode(IntPtr hdc, int mode);
        [DllImport("gdi32.dll")]
        internal static extern int SetTextColor(IntPtr hdc, int color);
        [DllImport("gdi32.dll")]
        internal static extern IntPtr CreateCompatibleDC(IntPtr hdc);
        [DllImport("gdi32.dll")]
        internal static extern IntPtr CreateCompatibleBitmap(IntPtr hdc, int w, int h);
        [DllImport("gdi32.dll")]
        internal static extern bool BitBlt(IntPtr dst, int x, int y, int w, int h, IntPtr src, int sx, int sy, uint rop);
        [DllImport("gdi32.dll")]
        internal static extern bool Rectangle(IntPtr hdc, int l, int t, int r, int b);
        [DllImport("gdi32.dll")]
        internal static extern IntPtr CreateRoundRectRgn(int l, int t, int r, int b, int w, int h);
        [DllImport("gdi32.dll")]
        internal static extern int SelectClipRgn(IntPtr hdc, IntPtr rgn);
        [DllImport("gdi32.dll")]
        internal static extern IntPtr GetStockObject(int index);
        [DllImport("gdi32.dll")]
        internal static extern IntPtr CreateDIBSection(IntPtr hdc, ref BITMAPINFO info, uint usage,
            out IntPtr bits, IntPtr section, uint offset);
        [DllImport("msimg32.dll")]
        internal static extern bool GradientFill(IntPtr hdc, IntPtr vertices, uint count,
            IntPtr mesh, uint meshCount, uint mode);
    }

    /// <summary>The window Discord sees: a real top-level window titled after the game.</summary>
    internal sealed class SpoofWindow
    {
        private const int CARD_INSET = 12;
        private const int CARD_RADIUS = 18;
        private const int DEFAULT_WIDTH = 760;
        private const int DEFAULT_HEIGHT = 520;
        private const int BORDER = 66;

        private readonly string _title;
        private readonly string _className;
        private readonly Native.WndProc _wndProc;
        private IntPtr _hwnd;
        private int _width = DEFAULT_WIDTH;
        private int _height = DEFAULT_HEIGHT;

        public SpoofWindow(string title)
        {
            _title = title;
            _className = "worthlesstaskWindow" + Environment.TickCount;
            // The delegate must outlive the window or the callback dies with the GC.
            _wndProc = OnMessage;
        }

        public void Run()
        {
            Native.WNDCLASS wc = new Native.WNDCLASS();
            wc.style = Native.CS_HREDRAW | Native.CS_VREDRAW;
            wc.lpfnWndProc = Marshal.GetFunctionPointerForDelegate(_wndProc);
            wc.hInstance = Native.GetModuleHandleW(null);
            wc.lpszClassName = Marshal.StringToHGlobalUni(_className);
            wc.hCursor = Native.LoadCursorW(IntPtr.Zero, (IntPtr)32512); // IDC_ARROW
            wc.hbrBackground = IntPtr.Zero; // every pixel is painted in WM_PAINT
            if (Native.RegisterClassW(ref wc) == 0)
                throw new InvalidOperationException("RegisterClassW failed: " + Marshal.GetLastWin32Error());

            // The detection contract. See the header comment.
            uint style = Native.WS_CAPTION | Native.WS_THICKFRAME | Native.WS_MINIMIZEBOX
                | Native.WS_SYSMENU | Native.WS_VISIBLE | Native.WS_CLIPCHILDREN | Native.WS_CLIPSIBLINGS;
            _hwnd = Native.CreateWindowExW(Native.WS_EX_APPWINDOW, _className, _title, style,
                unchecked((int)0x80000000), unchecked((int)0x80000000), _width, _height, IntPtr.Zero, IntPtr.Zero, wc.hInstance, IntPtr.Zero);
            if (_hwnd == IntPtr.Zero)
                throw new InvalidOperationException("CreateWindowExW failed: " + Marshal.GetLastWin32Error());
            // A GUI process started from a hidden/minimised console inherits that
            // show state, which would leave the window minimised. Show it plainly.
            Native.ShowWindow(_hwnd, 5); // SW_SHOW
            Native.SetForegroundWindow(_hwnd);

            Native.MSG msg;
            while (Native.GetMessageW(out msg, IntPtr.Zero, 0, 0) > 0)
            {
                Native.TranslateMessage(ref msg);
                Native.DispatchMessageW(ref msg);
            }
        }

        private IntPtr OnMessage(IntPtr hwnd, int msg, IntPtr wParam, IntPtr lParam)
        {
            switch (msg)
            {
                case Native.WM_PAINT:
                    Paint(hwnd);
                    return IntPtr.Zero;
                case Native.WM_ERASEBKGND:
                    return new IntPtr(1);
                case Native.WM_NCCALCSIZE:
                    // The client area is the whole window: the card is the only chrome.
                    return IntPtr.Zero;
                case Native.WM_CLOSE:
                    Native.DestroyWindow(hwnd);
                    return IntPtr.Zero;
                case Native.WM_DESTROY:
                    Native.PostQuitMessage(0);
                    return IntPtr.Zero;
                default:
                    return Native.DefWindowProcW(hwnd, msg, wParam, lParam);
            }
        }

        private static int Rgb(int r, int g, int b) { return r | (g << 8) | (b << 16); }

        private void Paint(IntPtr hwnd)
        {
            Native.PAINTSTRUCT ps;
            IntPtr hdc = Native.BeginPaint(hwnd, out ps);
            Native.RECT client;
            Native.GetClientRect(hwnd, out client);
            _width = client.Width;
            _height = client.Height;

            IntPtr mem = Native.CreateCompatibleDC(hdc);
            IntPtr bmp = Native.CreateCompatibleBitmap(hdc, Math.Max(1, _width), Math.Max(1, _height));
            IntPtr old = Native.SelectObject(mem, bmp);

            Vertical(mem, 0, 0, _width, _height, Rgb(17, 18, 21), Rgb(8, 9, 10));
            int inset = CARD_INSET;
            Rounded(mem, inset, inset, _width - inset, _height - inset, CARD_RADIUS, Rgb(24, 25, 29));
            Vertical(mem, inset, inset, _width - inset, _height - inset, Rgb(28, 29, 34), Rgb(16, 17, 20));
            // Sidebar sheet, then the bright top hairline of the card.
            Vertical(mem, inset, inset + BORDER, inset + BORDER, _height - inset, Rgb(30, 32, 37), Rgb(16, 17, 20));
            HLine(mem, inset, inset + BORDER, _width - inset, inset + BORDER, Rgb(48, 51, 58));
            HLine(mem, inset + BORDER, inset, inset + BORDER, _height - inset, Rgb(58, 60, 68));

            IntPtr font = Native.CreateFontW(-32, 0, 0, 0, 600, 0, 0, 0, Native.DEFAULT_CHARSET, 0, 0,
                Native.CLEARTYPE_QUALITY, 0, "Segoe UI");
            IntPtr oldFont = Native.SelectObject(mem, font);
            Native.SetBkMode(mem, Native.TRANSPARENT);
            Native.SetTextColor(mem, Rgb(238, 240, 244));
            Native.RECT box = new Native.RECT();
            box.Left = inset + 18; box.Top = inset + 12;
            box.Right = _width - 200; box.Bottom = box.Top + 26;
            Native.DrawTextW(mem, _title, -1, ref box,
                Native.DT_LEFT | Native.DT_VCENTER | Native.DT_SINGLELINE | Native.DT_NOPREFIX);

            Native.RECT hero = new Native.RECT();
            hero.Left = inset + BORDER + 24; hero.Top = inset + 80;
            hero.Right = _width - inset - 24; hero.Bottom = hero.Top + 40;
            Native.SetTextColor(mem, Rgb(255, 145, 55));
            Native.DrawTextW(mem, "Нет связи с Discord", -1, ref hero,
                Native.DT_LEFT | Native.DT_VCENTER | Native.DT_SINGLELINE | Native.DT_NOPREFIX);
            Native.SelectObject(mem, oldFont);
            Native.DeleteObject(font);

            Native.BitBlt(hdc, 0, 0, _width, _height, mem, 0, 0, Native.SRCCOPY);
            Native.SelectObject(mem, old);
            Native.DeleteObject(bmp);
            Native.DeleteObject(mem);
            Native.EndPaint(hwnd, ref ps);
        }

        private static void Vertical(IntPtr hdc, int l, int t, int r, int b, int top, int bottom)
        {
            IntPtr vertices = Marshal.AllocHGlobal(Marshal.SizeOf(typeof(Native.TRIVERTEX)) * 2);
            IntPtr mesh = Marshal.AllocHGlobal(Marshal.SizeOf(typeof(Native.GRADIENT_RECT)));
            try
            {
                Native.TRIVERTEX v0 = new Native.TRIVERTEX
                { x = l, y = t, Red = (short)(top << 8), Green = (short)((top >> 8 & 0xFF) << 8), Blue = (short)((top >> 16 & 0xFF) << 8), Alpha = -1 };
                Native.TRIVERTEX v1 = new Native.TRIVERTEX
                { x = r, y = b, Red = (short)(bottom << 8), Green = (short)((bottom >> 8 & 0xFF) << 8), Blue = (short)((bottom >> 16 & 0xFF) << 8), Alpha = -1 };
                Marshal.StructureToPtr(v0, vertices, false);
                Marshal.StructureToPtr(v1, IntPtr.Add(vertices, Marshal.SizeOf(typeof(Native.TRIVERTEX))), false);
                uint meshValue = (1u << 16) | 1u; // UpperLeft=1, LowerRight=1
                Marshal.WriteInt32(mesh, 0, unchecked((int)meshValue));
                Native.GradientFill(hdc, vertices, 2, mesh, 1, Native.GRADIENT_FILL_RECT_V);
            }
            finally
            {
                Marshal.FreeHGlobal(vertices);
                Marshal.FreeHGlobal(mesh);
            }
        }

        private static void Rounded(IntPtr hdc, int l, int t, int r, int b, int radius, int color)
        {
            IntPtr brush = Native.CreateSolidBrush((uint)color);
            IntPtr old = Native.SelectObject(hdc, brush);
            IntPtr pen = Native.SelectObject(hdc, Native.GetStockObject(Native.NULL_BRUSH));
            IntPtr region = Native.CreateRoundRectRgn(l, t, r + 1, b + 1, radius * 2, radius * 2);
            Native.SelectClipRgn(hdc, region);
            Native.Rectangle(hdc, l, t, r, b);
            Native.SelectClipRgn(hdc, IntPtr.Zero);
            Native.DeleteObject(region);
            Native.SelectObject(hdc, old);
            Native.SelectObject(hdc, pen);
            Native.DeleteObject(brush);
        }

        private static void HLine(IntPtr hdc, int x1, int y1, int x2, int y2, int color)
        {
            IntPtr brush = Native.CreateSolidBrush((uint)color);
            IntPtr oldBrush = Native.SelectObject(hdc, brush);
            IntPtr pen = CreatePen(0, 1, color);
            IntPtr oldPen = Native.SelectObject(hdc, pen);
            MoveToEx(hdc, x1, y1, IntPtr.Zero);
            LineTo(hdc, x2, y2);
            Native.SelectObject(hdc, oldPen);
            Native.SelectObject(hdc, oldBrush);
            Native.DeleteObject(pen);
            Native.DeleteObject(brush);
        }

        [DllImport("gdi32.dll")]
        private static extern IntPtr CreatePen(int style, int width, int color);
        [DllImport("gdi32.dll")]
        private static extern bool MoveToEx(IntPtr hdc, int x, int y, IntPtr none);
        [DllImport("gdi32.dll")]
        private static extern bool LineTo(IntPtr hdc, int x, int y);
    }

    internal static class Program
    {
        private static int Main(string[] args)
        {
            string title = args.Length > 0 ? args[0] : "ARKNIGHTS: ENDFIELD";
            try
            {
                new SpoofWindow(title).Run();
                return 0;
            }
            catch (Exception error)
            {
                Console.Error.WriteLine("launcher failed: " + error);
                return 2;
            }
        }
    }
}
