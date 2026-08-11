# Core Siswa — Odoo Module

> Database siswa utama KodingYuk: data personal, enrollment kursus, ujian, dan portofolio.

**Platform:** Odoo 17  
**Departemen:** Academic  
**Repo:** `core_siswa_odoo_academic`  
**Status:** ![Status](https://img.shields.io/badge/status-active-brightgreen)

---

## Deskripsi

Modul data master siswa KodingYuk. Menyimpan semua data siswa aktif/non-aktif, enrollment ke kursus/program, rekap ujian, dan portofolio project. Menjadi dependency utama hampir semua modul akademik lainnya.

**User utama:** Admin Akademik, Trainer, Tim Operasional

## Hak Akses

- **Viewer:** membaca data akademik siswa tanpa mengubah record.
- **Trainer:** menjalankan ujian, penilaian, rapot, dan portofolio tanpa hak
  menghapus record akademik.
- **Manager:** mengelola master siswa, enrollment, konfigurasi, dan seluruh
  record operasional.

Internal user tanpa grup Students tidak dapat membuka modul. Matriks rinci dan
rencana record rule trainer tersedia di
[`docs/ACCESS_MATRIX.md`](docs/ACCESS_MATRIX.md). Prosedur pemulihan tersedia di
[`docs/ROLLBACK.md`](docs/ROLLBACK.md).

---

## Model Odoo

| Model | Label | Keterangan |
|---|---|---|
| `m.siswa` | Siswa | Data master siswa (nama, kontak, level, status) |
| `siswa.kursus.enrollment` | Enrollment | Data pendaftaran siswa ke program/kursus |
| `siswa.kursus.exam` | Ujian Siswa | Rekap hasil ujian siswa per modul |
| `student.portfolio.project` | Portofolio | Project portofolio yang dibuat siswa |

---

## Fitur Utama

- **Database Siswa:** Status aktif/inactive/cuti/lulus, level, jenis kelas (reguler/privat/online)
- **Enrollment:** Daftarkan siswa ke program kursus
- **Tracking Ujian:** Rekap nilai ujian per siswa per modul
- **Portofolio:** Catat project yang dibuat siswa sebagai output pembelajaran

---

## Instalasi

```bash
git clone https://github.com/kodingyuk/core_siswa_odoo_academic.git
```

**Depends:** `base`, `mail`, `contacts`

---

## Changelog

| Versi | Tanggal | Perubahan |
|---|---|---|
| 17.0.2.0.0 | 2026-08-11 | Viewer/Trainer/Manager ACL, menu guards, dan proteksi field sensitif |
| 17.0.1.0.2 | — | Tambah portofolio dan enrollment |
| 17.0.1.0.0 | — | Initial release |

---

## Maintainer

**Tim:** Technology & RnD — KodingYuk  
**Kontak:** support@kodingyuk.id
