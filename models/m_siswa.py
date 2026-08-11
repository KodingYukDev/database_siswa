# -*- coding: utf-8 -*-
from odoo import models, fields, api
import base64
import time
from ..lib.firebase_service import upload_file_to_firebase

class StudentProfile(models.Model):
    _name = 'm.siswa'
    _description = 'Profil Siswa'
    # Tambahkan chatter di bawah (log histori)
    _inherit = ['mail.thread', 'mail.activity.mixin']

    # --- Relasi dan Tipe Siswa ---
    tipe_siswa = fields.Selection(
        [
            ('privat', 'Privat'),
            ('online', 'Online'),
            ('reguler', 'Reguler'),
            ('ekskul', 'Ekstrakurikuler'),
        ],
        string='Tipe Siswa',
        default='privat',
        required=True,
        tracking=True
    )

    # --- Data Siswa ---
    image_1920 = fields.Image(string="Foto Profil Siswa", max_width=1920, max_height=1920)
    profile_image_url = fields.Char(string='URL Foto Profil (Cloud)', help='URL eksternal jika foto disimpan di Cloud Storage')
    name = fields.Char(string='Nama Siswa', required=True, tracking=True) # New direct name field
    nis = fields.Char(string='NIS', tracking=True)
    email = fields.Char(string='Email', tracking=True)
    password = fields.Char(
        string='Password',
        tracking=True,
        copy=False,
        groups='students.group_student_manager',
    )

    class_name = fields.Char(string='Kelas', help="Contoh: 2 SD, TK B")
    
    # Relasi ke Master Tingkat
    level_id = fields.Many2one(
        'm.level.siswa', 
        string='Level',
        tracking=True
    )
    
    join_date = fields.Date(
        string='Tanggal Pertama Masuk',
        default=fields.Date.context_today,
        tracking=True
    )
    
    # Relasi ke Master Jenis Kelas
    class_type_id = fields.Many2one(
        'm.class.type', 
        string='Jenis Kelas',
        tracking=True
    )

    jadwal_hari = fields.Selection(
        [
            ('senin', 'Senin'),
            ('selasa', 'Selasa'),
            ('rabu', 'Rabu'),
            ('kamis', 'Kamis'),
            ('jumat', 'Jumat'),
            ('sabtu', 'Sabtu'),
            ('minggu', 'Minggu'),
        ],
        string='Jadwal Hari',
        tracking=True
    )

    jadwal_jam = fields.Float(string='Jadwal Jam', tracking=True)

    # --- Data untuk Penagihan Otomatis ---
    skema_pembayaran = fields.Selection(
        [
            ('monthly', 'Bulanan (per 4 pertemuan)'),
            ('semester', 'Semester (per 12 pertemuan)')
        ],
        string='Skema Pembayaran',
        default='monthly',
        required=True,
        tracking=True
    )

    product_id = fields.Many2one(
        'product.product',
        string='Produk untuk Penagihan',
        help="Pilih produk yang akan digunakan saat membuat invoice untuk siswa ini."
    )

    jumlah_pertemuan_hadir = fields.Integer(
        string='Total Pertemuan Dihadiri',
        default=0,
        readonly=True,
        copy=False # Tidak ikut dicopy saat record diduplikasi
    )

    jumlah_pertemuan_ditagih = fields.Integer(
        string='Total Pertemuan Ditagih',
        default=0,
        readonly=True,
        copy=False # Tidak ikut dicopy saat record diduplikasi
    )
    
    # Relasi ke Orang Tua (res.partner) - now exclusively for parent
    parent_id = fields.Many2one(
        'res.partner', 
        string='Penanggung Jawab / Institusi',
        help="Pilih kontak Penanggung Jawab (Orang Tua atau Institusi/Sekolah) yang ada di modul Kontak."
    )
    
    # Ambil nomor telepon dari Orang Tua secara otomatis
    parent_contact = fields.Char(
        string='Contact Person (HP)',
        related='parent_id.phone', # Bisa diganti ke 'mobile'
        readonly=True
    )
    
    status = fields.Selection(
        [
            ('active', 'Siswa Aktif'),
            ('leave', 'Cuti'),
            ('graduated', 'Lulus'),
            ('inactive', 'Tidak Aktif'),
        ],
        string='Status',
        default='active',
        tracking=True
    )
    
    notes = fields.Text(string='Keterangan')

    # --- Kode Akses Dashboard ---
    access_code = fields.Char(
        string='Kode Akses Dashboard',
        copy=False,
        readonly=True,
        help='Kode akses siswa untuk login di Student Dashboard (berlaku untuk semua kursus)',
        groups='students.group_student_trainer',
    )
    access_code_active = fields.Boolean(
        string='Kode Akses Aktif',
        default=False,
        copy=False,
        groups='students.group_student_trainer',
    )

    enrollment_ids = fields.One2many(
        'siswa.kursus.enrollment',
        'siswa_id',
        string='Riwayat Kursus'
    )

    # --- Data Portofolio ---
    portfolio_slug = fields.Char(string='URL Slug Portofolio', tracking=True, help='Contoh: aril-saputra')
    bio_singkat = fields.Text(string='Bio Portofolio', tracking=True, help='Misal: Suka bikin game Roblox dan ahli Minecraft!')
    portfolio_project_ids = fields.One2many(
        'student.portfolio.project',
        'siswa_id',
        string='Daftar Karya/Proyek'
    )

    current_enrollment_id = fields.Many2one(
        'siswa.kursus.enrollment',
        string='Kursus Aktif Saat Ini',
        compute='_compute_current_enrollment',
        store=True
    )

    @api.depends('enrollment_ids.status')
    def _compute_current_enrollment(self):
        for student in self:
            active_enrollments = student.enrollment_ids.filtered(lambda e: e.status == 'aktif')
            if active_enrollments:
                student.current_enrollment_id = active_enrollments[0]
            else:
                student.current_enrollment_id = False

    def action_generate_access_code(self):
        """Generate a unique access code for the student (ST- prefix)."""
        import uuid
        self.ensure_one()
        code = 'ST-' + uuid.uuid4().hex[:6].upper()
        self.write({
            'access_code': code,
            'access_code_active': True,
        })
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Kode Akses Berhasil Digenerate',
                'message': 'Kode akses untuk siswa: %s' % code,
                'sticky': True,
                'type': 'success',
            }
        }

    def action_deactivate_access_code(self):
        self.ensure_one()
        self.write({'access_code_active': False})

    # --- SQL Constraints ---
    # No partner_id_uniq constraint as partner_id is now for parent and not unique per student profile
    _sql_constraints = [
        ('name_unique', 'unique(name, parent_id)', 'Nama siswa dengan orang tua yang sama harus unik!')
    ]

    @api.model_create_multi
    def create(self, vals_list):
        res = super(StudentProfile, self).create(vals_list)
        for rec, vals in zip(res, vals_list):
            if vals.get('image_1920'):
                rec._upload_image_to_bucket()
        return res

    def write(self, vals):
        res = super(StudentProfile, self).write(vals)
        if vals.get('image_1920'):
            self._upload_image_to_bucket()
        return res

    def _upload_image_to_bucket(self):
        for rec in self:
            if not rec.image_1920:
                continue
            try:
                # Siapkan data
                file_content = base64.b64decode(rec.image_1920)
                file_name = f"profile_{rec.id}_{int(time.time())}.png"
                dest_path = f"students/profiles/{rec.id}/{file_name}"
                
                # Upload
                url = upload_file_to_firebase(self.env, file_content, file_name, dest_path, 'image/png')
                
                # Update URL cloud tanpa menghapus binary. Field image_1920 tetap
                # dipakai sebagai preview utama di Odoo dan fallback aplikasi lain.
                # Gunakan super().write agar tidak memicu loop rekursif write()
                super(StudentProfile, rec).write({
                    'profile_image_url': url,
                })
            except Exception as e:
                # Jika gagal, biarkan tetap di Binary sebagai fallback
                pass
