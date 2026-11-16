# Rencana Pengecualian Audit — Repo `adminabsensi.smkn8medan.sch.id`

## Tujuan
Menambahkan `adminabsensi.smkn8medan.sch.id` ke daftar pengecualian di `audit.config.json` agar temuan ukuran besar (57 MB) tidak dilaporkan sebagai anomali audit.

## Temuan Penyebab Bengkak
- Folder `VIRTUAL_PRIVATE_SERVER/` (182 MB lokal) berisi backup proyek versi VPS, tidak dibungkus `.gitignore` utama, jadi ikut ter-commit ke riwayat Git.
- Folder `vendor/` (82 MB) dan `node_modules` (77 MB di dalam `VIRTUAL_PRIVATE_SERVER/`) sudah di `.gitignore`, tidak ikut ter-commit.
- SQL dump (`backup_20260722-1636.sql` 128 KB, `vps_backup.sql` 304 KB) relatif kecil, bukan penyebab utama.
- Kesimpulan: pembengkakan sengaja dari pencadangan folder proyek, bukan file biner aset besar tanpa LFS.

## Keputusan

| Keputusan | Nilai | Alasan |
|---|---|---|
| Aksi | Tambahkan `adminabsensi.smkn8medan.sch.id` ke `excluded_repos` di `audit.config.json` | Mirip pola `stream_drive` dan `ukmipolmed` |
| Repo diarsipkan | Ya (di GitHub) | Sudah final, tidak ada rencana update, perubahan terbaru ada di tangan orang lain |
| Konten | Konten unik, tidak boleh dihapus | Backup VPS disatukan ke satu subfolder `VIRTUAL_PRIVATE_SERVER/` |
| Migrasi LFS / pembersihan history | Tidak dilakukan | Repo diarsipkan, tidak akan diperbarui |

## Berkas yang perlu diedit (oleh agen implementasi)
- `audit.config.json` — tambahkan entri `adminabsensi.smkn8medan.sch.id` ke `excluded_repos`

## Contoh entri audit.config.json

```json
{
  "name": "adminabsensi.smkn8medan.sch.id",
  "reason": "Repo diarsipkan karena sudah final dan tidak akan diperbarui (perubahan terbaru ada di tangan orang lain). Ukuran besar (57 MB) disebabkan folder backup proyek versi VPS (`VIRTUAL_PRIVATE_SERVER/`) yang sengaja disatukan ke satu subfolder. Temuan ukuran besar dikecualikan dari anomali audit."
}
```

## Validasi
- `audit.config.json` tetap valid JSON
- `audit.py` memuat `adminabsensi.smkn8medan.sch.id` ke `EXCLUDED_REPOS` dan `EXCLUSION_REASONS`
- Laporan audit tidak lagi mencantumkan `adminabsensi.smkn8medan.sch.id` di bawah anomali ukuran besar

## Catatan
- Jika diinginkan nantinya, entri dapat dihapus dari `audit.config.json` untuk mengaktifkan kembali deteksi anomali.
