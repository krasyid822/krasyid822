# Rencana Reset Riwayat Commit — Repo `stream`

## Tujuan
Menghapus seluruh riwayat commit lama di repository `stream`, menyisakan satu commit baru yang berisi keadaan aktif (HEAD) saat ini. Tanpa backup, tanpa clone ulang, tanpa Git LFS.

## Repositori Sasaran
- `https://github.com/krasyid822/stream.git`
- Ukuran saat ini: ~36 GB

## Keputusan Desain

| Keputusan | Nilai | Alasan |
|---|---|---|
| Metode | `git checkout --orphan` + commit tunggal | Cepat, isi aktif dipertahankan sebagai satu commit, riwayat lama hilang |
| File yang dipertahankan | Semua file di HEAD saat ini | User hanya reset commit, tidak menghapus file aktif |
| Cadangan | Tidak | Per permintaan user |
| Clone working copy | Tidak | User sudah memiliki source terbaru secara lokal |
| Branch | Default branch saja | Sederhana |
| Force push | Ya (`git push --force origin <branch>`) | Riwayat ditulis ulang |

## Langkah Eksekusi (untuk agen implementasi)

1. **Masuk ke salinan lokal yang sudah ada** (path akan dikonfirmasi, lihat Open Questions)
   ```bash
   cd <path-salinan-lokal-stream>
   ```

2. **Verifikasi branch aktif dan status working tree**
   ```bash
   git status
   git branch --show-current
   ```

3. **Buat orphan branch dengan isi aktif**
   ```bash
   git checkout --orphan reset-history
   git add -A
   git commit -m "Reset riwayat commit, simpan keadaan aktif saja"
   ```

4. **Gantikan branch lama**
   ```bash
   git branch -D <branch-lama>
   git branch -m <branch-lama>
   ```

5. **Force push ke GitHub**
   ```bash
   git push --force origin <branch-lama>
   ```

6. **Verifikasi**
   ```bash
   git log --oneline   # harus hanya 1 commit
   ls                  # file aktif masih ada
   ```

## Risiko & Catatan
- Semua riwayat commit lama hilang permanen; tidak ada cadangan.
- Commit hash berubah sepenuhnya; siapa pun yang sudah clone harus clone ulang atau `git reset --hard origin/<branch>`.
- Jika ada branch lain selain default yang ingin dipertahankan, ulangi langkah 3-5 untuk branch tersebut.

## Open Questions (perlu konfirmasi sebelum implementasi)
1. Path lengkap salinan lokal repo `stream` yang sudah di-download? (Recommended: berikan path absolut)
2. Nama default branch yang digunakan? (Recommended: `main`)
