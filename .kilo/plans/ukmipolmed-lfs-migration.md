# Rencana Pengecualian Audit — Repo `ukmipolmed`

## Tujuan
Menambahkan `ukmipolmed` ke daftar pengecualian di `audit.config.json` agar ukuran besar (~1.7 GB) tidak dilaporkan sebagai anomali audit, karena repo diarsipkan dengan konten unik yang tidak boleh dihapus dan tidak akan diperbarui (terlalu besar untuk di cloning).

## Keputusan

| Keputusan | Nilai | Alasan |
|---|---|---|
| Aksi | Tambahkan `ukmipolmed` ke `excluded_repos` di `audit.config.json` | Cocok dengan pola `stream_drive` yang sudah ada |
| Repo diarsipkan | Ya (di GitHub) | Konten unik, tidak boleh dihapus, tidak akan diperbarui |
| Migrasi LFS | Tidak dilakukan | Terlalu besar untuk di cloning, tidak ingin merusak GitHub Pages |
| Penyimpanan | Tetap 1.7 GB | Tidak berubah; hanya disembunyikan dari temuan anomali audit |

## Berkas yang perlu diedit (oleh agen implementasi)

- `.kilo/plans/ukmipolmed-lfs-migration.md` — tandai rencana LFS sebagai dibatalkan/diganti
- `audit.config.json` — tambahkan entri `ukmipolmed` ke `excluded_repos`

## Contoh entri audit.config.json

```json
{
  "name": "ukmipolmed",
  "reason": "Repo diarsipkan karena menyimpan konten unik yang tidak boleh dihapus. Ukuran besar (~1.7 GB) diketahui sengaja dan tidak akan diperbarui karena terlalu besar untuk di cloning. Temuan ukuran besar dikecualikan dari anomali audit."
}
```

## Validasi
- `audit.config.json` tetap valid JSON
- `audit.py` memuat `ukmipolmed` ke `EXCLUDED_REPOS` dan `EXCLUSION_REASONS`
- Laporan audit tidak lagi mencantumkan `ukmipolmed` di bawah anomali ukuran besar

## Catatan
- Archiving di GitHub tidak mematikan GitHub Pages secara otomatis, tapi tidak dijamin; ukuran repo tetap 1.7 GB.
- Jika diinginkan nantinya, entri dapat dihapus dari `audit.config.json` untuk mengaktifkan kembali deteksi anomali.
