using System;
using System.IO;
using System.IO.Compression;
using System.Text;

namespace BiliGo
{
    // POSIX tar + UTF-8 PAX paths, using only the .NET runtime shipped with PowerShell.
    public static class UploadTar
    {
        static readonly Encoding Utf8 = new UTF8Encoding(false);

        static void Put(byte[] header, int offset, int length, string value)
        {
            byte[] bytes = Encoding.ASCII.GetBytes(value);
            if (bytes.Length > length) throw new InvalidDataException("Tar header field is too long.");
            Buffer.BlockCopy(bytes, 0, header, offset, bytes.Length);
        }

        static void Header(Stream stream, string name, long size, long modified, char type)
        {
            byte[] header = new byte[512];
            Put(header, 0, 100, name);
            Put(header, 100, 8, "0000644\0");
            Put(header, 108, 8, "0000000\0");
            Put(header, 116, 8, "0000000\0");
            Put(header, 124, 12, Convert.ToString(size, 8).PadLeft(11, '0') + "\0");
            Put(header, 136, 12, Convert.ToString(modified, 8).PadLeft(11, '0') + "\0");
            for (int index = 148; index < 156; index++) header[index] = 32;
            header[156] = (byte)type;
            Put(header, 257, 6, "ustar\0");
            Put(header, 263, 2, "00");
            int checksum = 0;
            foreach (byte value in header) checksum += value;
            Put(header, 148, 8, Convert.ToString(checksum, 8).PadLeft(6, '0') + "\0 ");
            stream.Write(header, 0, header.Length);
        }

        static void Pad(Stream stream, long length)
        {
            int padding = (int)((512 - length % 512) % 512);
            if (padding != 0) stream.Write(new byte[padding], 0, padding);
        }

        static byte[] PaxPath(string path)
        {
            string payload = " path=" + path + "\n";
            int length = Utf8.GetByteCount(payload) + 1;
            for (;;)
            {
                byte[] record = Utf8.GetBytes(length.ToString() + payload);
                if (record.Length == length) return record;
                length = record.Length;
            }
        }

        public static void Create(string destination, string project, string[] relativePaths)
        {
            DateTime epoch = new DateTime(1970, 1, 1, 0, 0, 0, DateTimeKind.Utc);
            using (FileStream output = File.Create(destination))
            using (GZipStream gzip = new GZipStream(output, CompressionMode.Compress))
            {
                int number = 0;
                foreach (string relative in relativePaths)
                {
                    string path = relative.Replace('\\', '/');
                    string source = Path.Combine(project, relative);
                    FileInfo info = new FileInfo(source);
                    long modified = Math.Max(0, (long)(info.LastWriteTimeUtc - epoch).TotalSeconds);
                    string headerName = path;
                    if (Encoding.ASCII.GetString(Encoding.ASCII.GetBytes(path)) != path || Utf8.GetByteCount(path) > 100)
                    {
                        byte[] record = PaxPath(path);
                        Header(gzip, "PaxHeaders/" + number, record.Length, modified, 'x');
                        gzip.Write(record, 0, record.Length);
                        Pad(gzip, record.Length);
                        headerName = "entry-" + number;
                    }
                    using (FileStream input = File.OpenRead(source))
                    {
                        Header(gzip, headerName, input.Length, modified, '0');
                        input.CopyTo(gzip);
                        Pad(gzip, input.Length);
                    }
                    number++;
                }
                gzip.Write(new byte[1024], 0, 1024);
            }
        }
    }
}
